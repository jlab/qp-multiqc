# -----------------------------------------------------------------------------
# Copyright (c) 2024--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Copyright (c) 2025, Dein Name oder Projekt
# Distributed under the terms of the BSD 3-Clause License.
# -----------------------------------------------------------------------------

import os
import glob
import subprocess
from concurrent.futures import ThreadPoolExecutor
from os.path import join
from qiita_client import ArtifactInfo
from qiita_client.util import system_call
import qiita_files
from qiita_files.demux import to_per_sample_files


def run_fastqc(file, fastqc_env, fastqc_outdir):
    """Ein einzelner FastQC-Lauf"""
    cmd = ["conda", "run", "-n", fastqc_env, "fastqc", file, "--outdir", fastqc_outdir]
    subprocess.run(cmd, check=True)


def run_multiqc(qclient, job_id, parameters, out_dir):
    """Erstellt einen MultiQC-Report aus einer .demux-Datei"""
    NUM_STEPS = 5
    qclient.update_job_step(job_id, f"Step 1 of {NUM_STEPS}: Vorbereitung")

    # Eingabeparameter
    demux_fp = parameters['Input demux artifact']
    fastqc_env = parameters['FastQC conda env name']
    multiqc_env = parameters['MultiQC conda env name']
    min_per_sample = parameters.get('Minimum samples per feature', 1)
    threads = parameters.get('Number of parallel FastQC jobs', 4)

    # Arbeitsverzeichnisse
    split_outdir = join(out_dir, 'split_fastq')
    fastqc_outdir = join(out_dir, 'fastqc_reports')
    multiqc_outdir = join(out_dir, 'multiqc_report')

    os.makedirs(split_outdir, exist_ok=True)
    os.makedirs(fastqc_outdir, exist_ok=True)
    os.makedirs(multiqc_outdir, exist_ok=True)

    # Schritt 2: .demux splitten
    qclient.update_job_step(job_id, f"Step 2 of {NUM_STEPS}: Splitten der Demux-Datei")
    to_per_sample_files(demux_fp, out_dir=split_outdir, out_format='fastq')

    # Alle FASTQ-Dateien suchen
    suffixes = ("*.fastq", "*.fq", "*.fastq.gz", "*.fq.gz")
    fastq_files = [f for pattern in suffixes for f in glob.glob(join(split_outdir, pattern))]
    if len(fastq_files) == 0:
        return False, None, "Keine FASTQ-Dateien gefunden."

    # Schritt 3: FastQC parallel ausführen
    qclient.update_job_step(job_id, f"Step 3 of {NUM_STEPS}: FastQC auf {len(fastq_files)} Dateien starten (parallel)")
    with ThreadPoolExecutor(max_workers=threads) as executor:
        for file in fastq_files:
            executor.submit(run_fastqc, file, fastqc_env, fastqc_outdir)

    # Schritt 4: MultiQC erstellen
    qclient.update_job_step(job_id, f"Step 4 of {NUM_STEPS}: MultiQC Report erstellen")
    cmd_multiqc = f"conda run -n {multiqc_env} multiqc -o {multiqc_outdir} {fastqc_outdir}"
    std_out, std_err, return_code = system_call(cmd_multiqc)
    if return_code != 0:
        return False, None, f"Fehler bei MultiQC: {std_err}"

    # Schritt 5: Outputs vorbereiten
    qclient.update_job_step(job_id, f"Step 5 of {NUM_STEPS}: Outputs zurückgeben")
    outputs = [
        (join(multiqc_outdir, "multiqc_report.html"), 'html'),
        (join(multiqc_outdir, "multiqc_data"), 'directory'),
    ]

    ainfo = [ArtifactInfo('MultiQC report', 'html', outputs)]

    return True, ainfo, ""

