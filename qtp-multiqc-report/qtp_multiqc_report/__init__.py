from qiita_client import QiitaTypePlugin, QiitaArtifactType
from .validate import validate

artifact_types = [
    QiitaArtifactType(
        'MultiQCReport', # name
        'Aggregated QC report from FastQC + MultiQC',
        False,   # EBI submission
        False,   # VAMPS submission
        False,   # user uploadable
        [
            ('plain_text', True),
            ('directory', True),
        ]
    )
]


# The visualization is the summary itself, so we don't need a
# generate_html_summary function. However, the plugins requires to
# register a function for it
def generate_html_summary(qclient, job_id, parameters, out_dir):
    return True, None, ""


plugin = QiitaTypePlugin(
    'MultiQC Type Plugin',
    '0.1.0',
    'Adds MultiQCReport artifact type to Qiita',
    validate,
    generate_html_summary,
    artifact_types
)