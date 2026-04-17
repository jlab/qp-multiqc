from qiita_client import ArtifactInfo
from json import loads
from os.path import basename, exists, isdir, join



def validate(qclient, job_id, parameters, out_dir):
    """
    Create MultiQCReport artifact
    """

    qclient.update_job_step(job_id, "Collecting inputs")

    artifact_type = parameters['artifact_type']
    files = loads(parameters['files'])

    if artifact_type != "MultiQCReport":
        return False, None, f"Unsupported type {artifact_type}"

    report_inputs = files.get('plain_text', [])
    if not report_inputs:
        return False, None, "No report file provided for MultiQCReport"

    if not exists(out_dir) or not isdir(out_dir):
        return False, None, f"Output directory does not exist: {out_dir}"

    # Prefer the canonical MultiQC file when available.
    report_fp = next((fp for fp in report_inputs
                      if basename(fp) == 'multiqc_report.html'),
                     report_inputs[0])
    # The report and summary are copied into the same artifact directory;
    # use a stable local filename rather than a job-specific relative path.
    iframe_src = basename(report_fp)

    summary_fp = join(out_dir, "summary.html")
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Summary</title>
    <style>
        html, body {{
            margin: 0;
            height: 100%;
            display: flex;
            flex-direction: column;
        }}
        h1 {{
            margin: 0;
            padding: 1rem;
            background-color: #f0f0f0;
            font-family: sans-serif;
        }}
        iframe {{
            flex: 1;
            width: 100%;
            border: none;
        }}
    </style>
</head>
<body>
    <h1>Summary</h1>
    <iframe src="{iframe_src}"></iframe>
</body>
</html>
"""
    with open(summary_fp, "w") as f:
        f.write(html_content)

    # Flatten file structure and avoid duplicate summary entries if present.
    filepaths = [(fp, t) for t, fps in files.items() for fp in fps]
    filepaths = [(fp, t) for fp, t in filepaths
                 if not (t == 'plain_text' and basename(fp) == 'summary.html')]

    # Register HTML summary for GUI rendering.
    # Do not add html_summary_dir for the same directory path that is already
    # present as 'directory', because duplicate path registrations can stall
    # job completion in Qiita's validator flow.
    filepaths.append((summary_fp, 'html_summary'))

    artifact_name = parameters.get('name', 'MultiQC Report')
    return True, [ArtifactInfo(artifact_name, 'MultiQCReport', filepaths)], ""