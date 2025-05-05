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

# TODO: extract function into bash script
def run_fastqc(file, fastqc_env, fastqc_outdir):
    """Runs FastQC on a single file."""
    cmd = ["conda", "run", "-n", fastqc_env, "fastqc", file, "--outdir", fastqc_outdir]
    subprocess.run(cmd, check=True)

def run_multiqc(qclient, job_id, parameters, out_dir):
    """Generates a MultiQC report from a demux artifact."""

    NUM_STEPS = 5

    # Step 1: Preparation
    qclient.update_job_step(job_id, f"Step 1 of {NUM_STEPS}: Preparation")

    # Input parameters
    demux_fp = parameters['Input demux artifact']
    fastqc_env = parameters['FastQC conda env name']
    multiqc_env = parameters['MultiQC conda env name']
    threads = parameters.get('Number of parallel FastQC jobs', 4)

    # Create working directories
    split_outdir = join(out_dir, 'split_fastq')
    fastqc_outdir = join(out_dir, 'fastqc_reports')
    multiqc_outdir = join(out_dir, 'multiqc_report')

    os.makedirs(split_outdir, exist_ok=True)
    os.makedirs(fastqc_outdir, exist_ok=True)
    os.makedirs(multiqc_outdir, exist_ok=True)

    # Step 2: Split demux file into per-sample fastq
    qclient.update_job_step(job_id, f"Step 2 of {NUM_STEPS}: Split demux file")
    to_per_sample_files(demux_fp, out_dir=split_outdir, out_format='fastq')

    # Find all FASTQ files
    suffixes = ("*.fastq", "*.fq", "*.fastq.gz", "*.fq.gz")
    fastq_files = [f for pattern in suffixes for f in glob.glob(join(split_outdir, pattern))]

    if not fastq_files:
        return False, None, "No FASTQ files found after splitting demux."

    # Step 3: Run FastQC in parallel
    qclient.update_job_step(job_id, f"Step 3 of {NUM_STEPS}: Run FastQC")
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(run_fastqc, file, fastqc_env, fastqc_outdir) for file in fastq_files]
        for future in futures:
            future.result()  # collect exceptions early

    # Step 4: Run MultiQC
    qclient.update_job_step(job_id, f"Step 4 of {NUM_STEPS}: Run MultiQC")
    cmd_multiqc = f"conda run -n {multiqc_env} multiqc -o {multiqc_outdir} {fastqc_outdir}"
    std_out, std_err, return_code = system_call(cmd_multiqc)

    if return_code != 0:
        return False, None, f"Error running MultiQC:\n{std_err}"

    # Cleanup: Remove FastQC reports
    try:
        shutil.rmtree(fastqc_outdir)
    except OSError as e:
        print(f"Warning: Failed to delete FastQC output folder: {e}")

    # Cleanup: Remove split FASTQ files
    try:
        shutil.rmtree(split_outdir)
    except OSError as e:
        print(f"Warning: Failed to delete split FASTQ files: {e}")

    # Step 5: Return outputs
    qclient.update_job_step(job_id, f"Step 5 of {NUM_STEPS}: Returning outputs")
    outputs = [
        (join(multiqc_outdir, "multiqc_report.html"), 'html'),
        (join(multiqc_outdir, "multiqc_data"), 'directory'),
    ]
    ainfo = [ArtifactInfo('MultiQC Report', 'html', outputs)]

    return True, ainfo, ""

# TODO: Add generate_summary_html function???
def generate_summary_html(out_dir):
    """Generates a summary HTML file from the MultiQC report."""
    pass
