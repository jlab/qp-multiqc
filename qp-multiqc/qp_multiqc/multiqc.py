import os
import glob
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from os.path import join
from qiita_client import ArtifactInfo
from qiita_client.util import system_call
import qiita_files
from qiita_files.demux import to_per_sample_files


SEQUENCE_EXTS = ('.demux', '.fastq', '.fq', '.fastq.gz', '.fq.gz', '.qual', '.fna')


def _collect_artifact_file_entries(obj, inferred_type=None):
    """Collect (filepath, filepath_type) pairs from nested artifact payloads."""
    entries = []

    if isinstance(obj, dict):
        # Common shape for Qiita artifact endpoints.
        files_value = obj.get('files')
        if files_value is not None:
            entries.extend(_collect_artifact_file_entries(files_value))

        for key, value in obj.items():
            if key == 'files':
                continue

            if isinstance(value, (dict, list, tuple)):
                entries.extend(_collect_artifact_file_entries(value, key))
            elif isinstance(value, str) and ('/' in value or value.endswith(SEQUENCE_EXTS)):
                entries.append((value, inferred_type or key))

    elif isinstance(obj, (list, tuple)):
        for item in obj:
            if isinstance(item, str):
                entries.append((item, inferred_type))
            elif isinstance(item, (list, tuple)) and item:
                fp = item[0]
                ftype = item[1] if len(item) > 1 and isinstance(item[1], str) else inferred_type
                if isinstance(fp, str):
                    entries.append((fp, ftype))
            elif isinstance(item, dict):
                fp = item.get('filepath') or item.get('path') or item.get('fp')
                ftype = item.get('filepath_type') or item.get('type') or inferred_type
                if isinstance(fp, str):
                    entries.append((fp, ftype))
                entries.extend(_collect_artifact_file_entries(item, inferred_type))

    return entries


def _resolve_existing_filepath(fp):
    """Resolve relative artifact filepaths to real paths inside /qiita_data."""
    if not fp:
        return None

    if os.path.exists(fp):
        return fp

    candidates = [
        join('/qiita_data', fp),
        join('/qiita_data/raw_data', fp),
        join('/qiita_data/preprocessed', fp),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand

    # Last fallback for test fixtures with relative DB paths.
    base = os.path.basename(fp)
    for cand in glob.glob(f'/qiita_data/**/{base}', recursive=True):
        if os.path.exists(cand):
            return cand

    return None


def _select_demux_filepath(artifact_payload):
    """Pick the most suitable demux/FASTQ filepath from artifact metadata."""
    entries = _collect_artifact_file_entries(artifact_payload)

    if not entries:
        return None, None, []

    preferred_types = [
        'preprocessed_demux',
        'preprocessed_fastq',
        'raw_forward_seqs',
        'raw_reverse_seqs',
        'raw_barcodes',
        'plain_text',
    ]
    preferred_exts = [
        '.demux',
        '.fastq.gz',
        '.fq.gz',
        '.fastq',
        '.fq',
        '.qual',
        '.fna',
    ]

    def _rank(entry):
        fp, ftype = entry
        ftype = (ftype or '').lower()
        fp_l = fp.lower()

        type_rank = next((i for i, t in enumerate(preferred_types)
                          if t == ftype), len(preferred_types))
        ext_rank = next((i for i, e in enumerate(preferred_exts)
                         if fp_l.endswith(e)), len(preferred_exts))

        # Prefer absolute paths when ties occur.
        abs_rank = 0 if fp.startswith('/') else 1
        return (type_rank, ext_rank, abs_rank, fp)

    ranked = sorted(entries, key=_rank)

    # Pick first ranked path that can be resolved in this container.
    for fp, ftype in ranked:
        resolved = _resolve_existing_filepath(fp)
        if resolved is not None:
            return resolved, ftype, ranked

    # If nothing resolves, keep first sequence-looking candidate for diagnostics.
    for fp, ftype in ranked:
        if fp.lower().endswith(tuple(preferred_exts)):
            return fp, ftype, ranked

    return None, None, ranked


def _resolve_artifact_input_filepath(qclient, artifact_id, max_depth=3, visited=None):
    """Resolve a usable input filepath from artifact and (if needed) parent artifacts."""
    if visited is None:
        visited = set()

    artifact_id = str(artifact_id)
    if artifact_id in visited or max_depth < 0:
        return None, None, None, []
    visited.add(artifact_id)

    artifact_payload = qclient.get("/qiita_db/artifacts/%s/" % artifact_id)
    fp, ftype, ranked = _select_demux_filepath(artifact_payload)
    if fp is not None:
        return fp, ftype, artifact_id, ranked

    parents = artifact_payload.get('parents', []) or []
    for parent_id in parents:
        p_fp, p_type, src_artifact, p_ranked = _resolve_artifact_input_filepath(
            qclient, parent_id, max_depth=max_depth - 1, visited=visited)
        if p_fp is not None:
            return p_fp, p_type, src_artifact, p_ranked

    return None, None, artifact_id, ranked

# TODO: extract function into bash script
def run_fastqc(file, fastqc_outdir):
    """Runs FastQC on a single file."""
    cmd = ["fastqc", file, "--outdir", fastqc_outdir]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        msg = (
            f"FastQC failed for input: {file}\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout.strip()}\n"
            f"STDERR:\n{result.stderr.strip()}"
        )
        raise RuntimeError(msg)

def run_multiqc(qclient, job_id, parameters, out_dir):
    """Generates a MultiQC report from a demux artifact."""

    NUM_STEPS = 5

    # Step 1: Preparation
    qclient.update_job_step(job_id, f"Step 1 of {NUM_STEPS}: Preparation")

    # Input parameters
    artifact_id = parameters['Demultiplexed sequences']
    demux_fp, input_type, source_artifact_id, ranked_candidates = (
        _resolve_artifact_input_filepath(qclient, artifact_id)
    )
    if demux_fp is None:
        preview = ", ".join(
            f"{fp} ({ftype})" for fp, ftype in ranked_candidates[:10]
        )
        if not preview:
            preview = "<none>"
        return False, None, (
            f"Could not determine a demux/FASTQ filepath for artifact "
            f"{artifact_id}. Candidates: {preview}"
        )
    raw_threads = parameters.get('Number of parallel FastQC jobs', 4)
    try:
        threads = int(raw_threads)
    except (TypeError, ValueError):
        return False, None, (
            "'Number of parallel FastQC jobs' must be an integer, got: "
            f"{raw_threads!r}"
        )

    if threads < 1:
        return False, None, (
            "'Number of parallel FastQC jobs' must be >= 1, got: "
            f"{threads}"
        )

    # Create working directories
    split_outdir = join(out_dir, 'split_fastq')
    fastqc_outdir = join(out_dir, 'fastqc_reports')
    multiqc_outdir = join(out_dir, 'multiqc_report')

    os.makedirs(fastqc_outdir, exist_ok=True)
    os.makedirs(multiqc_outdir, exist_ok=True)

    # Step 2: Prepare FASTQ inputs
    split_required = (
        (input_type or '').lower() == 'preprocessed_demux' or
        demux_fp.lower().endswith('.demux')
    )
    if split_required:
        qclient.update_job_step(job_id, f"Step 2 of {NUM_STEPS}: Split demux file")
        os.makedirs(split_outdir, exist_ok=True)
        to_per_sample_files(demux_fp, out_dir=split_outdir, out_format='fastq')

        suffixes = ("*.fastq", "*.fq", "*.fastq.gz", "*.fq.gz")
        fastq_files = [
            f for pattern in suffixes for f in glob.glob(join(split_outdir, pattern))
        ]
        if not fastq_files:
            return False, None, (
                f"No FASTQ files found after splitting demux: {demux_fp} "
                f"(artifact {source_artifact_id})"
            )
    else:
        qclient.update_job_step(job_id, f"Step 2 of {NUM_STEPS}: Prepare FASTQ input")
        fastq_files = [demux_fp]

    # Step 3: Run FastQC in parallel
    qclient.update_job_step(job_id, f"Step 3 of {NUM_STEPS}: Run FastQC")
    try:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(run_fastqc, file, fastqc_outdir)
                       for file in fastq_files]
            for future in futures:
                future.result()  # collect exceptions early
    except Exception as e:
        return False, None, str(e)

    # Step 4: Run MultiQC
    qclient.update_job_step(job_id, f"Step 4 of {NUM_STEPS}: Run MultiQC")
    cmd_multiqc = f"multiqc -o {multiqc_outdir} {fastqc_outdir}"
    std_out, std_err, return_code = system_call(cmd_multiqc)

    if return_code != 0:
        return False, None, f"Error running MultiQC:\n{std_err}"

    # Cleanup: Remove FastQC reports
    try:
        shutil.rmtree(fastqc_outdir)
    except OSError as e:
        print(f"Warning: Failed to delete FastQC output folder: {e}")

    # Cleanup: Remove split FASTQ files
    if os.path.exists(split_outdir):
        try:
            shutil.rmtree(split_outdir)
        except OSError as e:
            print(f"Warning: Failed to delete split FASTQ files: {e}")

    # Step 5: Return outputs
    qclient.update_job_step(job_id, f"Step 5 of {NUM_STEPS}: Returning outputs")
    outputs = [
        (join(multiqc_outdir, "multiqc_report.html"), 'plain_text'),
        (join(multiqc_outdir, "multiqc_data"), 'directory'),
    ]
    ainfo = [ArtifactInfo('MultiQC Report', 'MultiQCReport', outputs)]

    return True, ainfo, ""

# TODO: Add generate_summary_html function???
def generate_summary_html(out_dir):
    """Generates a summary HTML file from the MultiQC report."""
    pass
