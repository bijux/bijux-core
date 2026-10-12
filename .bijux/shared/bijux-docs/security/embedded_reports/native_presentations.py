"""Finite retained native presentations; source output never selects its own exemption.

The historical Nordic document exceeds its own 512 KiB bootstrap claim by 2011
bytes. Its exact reviewed presentation alone has a 526299-byte publication cap;
all other documents retain 512 KiB. This does not validate scientific results or
repair the historical producer budget. The Swedish chart has no bootstrap: its
original script and six immutable local data files form a separate finite recipe.
"""
import subprocess

from .contract import AdmissionError, canonical, digest, inspect_data, json_data, read_owned

SITE = "https://bijux.io/bijux-pollenomics/"
NORDIC_SOURCE = "docs/report/regions/nordic/nordic_map.html"
NORDIC_OUTPUT = "report/regions/nordic/nordic_map.html"
NORDIC_SHA = "10058ef43fa541ed886bc41f6ac2f95d957c15dc1b61acd9e72f87617b5327d3"
NORDIC_BYTES = 526299
SEQUENCE_SOURCE = "docs/report/pollen-reconstruction/swedish-native-sequences/index.html"
SEQUENCE_OUTPUT = "report/pollen-reconstruction/swedish-native-sequences/index.html"
SEQUENCE_SHA = "a07d47e01f5f2b63349b3f381d97bc13bd64845b1ef8785907f77558311432ec"
SEQUENCE_SCRIPT = "a214419074c2f95c9a0f994e38208320b775220ea2ad9dbcadc53758c54d4b62"
NORDIC_RECIPE_SHA = 'e51aff8dd05fda141df8342713d31627cb2c4dbe484502f95f86569c917a6d63'
NORDIC_RESOURCES_SHA = '15726ce845198cb23fa0fe391f456e27915b929e8a657aa42bc6826e47fd568b'
NORDIC_BOOTSTRAP_SHA = '72639346ed1d3c1edf2e4114eeb117c072275e281956b5537e1097e5771204b0'
NORDIC_SCRIPT_SHA = '8c7d17eeb9e2f39b2125d3841a8324129a8e773eea4d782c8ba4e8e2f878a9b1'
NORDIC_PRODUCERS = {'packages/bijux-pollenomics/src/bijux_pollenomics/reporting/map_document/assets/document.html': '8148da4b439da1deea7eca7ec355ab106ee31d16d564860ddf375ba783a72ae6',
 'packages/bijux-pollenomics/src/bijux_pollenomics/reporting/map_document/assets/source-record-export.js': '733d6c172381f2d9555cb7bf4290f48e97d8bc8dceb57b3697676d97e78ce43b',
 'packages/bijux-pollenomics/src/bijux_pollenomics/reporting/map_document/assets/url-state.js': '7f112ee6e727d3e51058724f2c80af9b610890ce793110f6404562800d2be682'}
SEQUENCE_FILES = {'chronology-controls.json': {'bytes': 41094,
                              'sha256': '26b31797bfc6f21d324324af3a90602bb8b6c93e4c8e5ae486ec4adc7cb44cd2'},
 'manifest.json': {'bytes': 1158,
                   'sha256': '9f9a29740c56ec64dc089e50d57514071146fc3945a90d3e3b270dedfb5e722b'},
 'map-summary.geojson': {'bytes': 1581,
                         'sha256': '5439b70710442878bf66a9ea6e05431976a5ed4f23196f49d54e59100fd3b7f2'},
 'observations.json': {'bytes': 2399919,
                       'sha256': '7ffa39bb8436aa16a958bf274a1f823e6b0de93fe1dfe5eb76061c43646cbf8a'},
 'samples.json': {'bytes': 124912,
                  'sha256': 'abbeca209bed0d5464bbe18b4c812cdd3b8ffcdad40979efd2783ede5199c45d'},
 'sites.json': {'bytes': 1736,
                'sha256': '9956683a701d5ed576836e1f37d894dce81d8e6cb1050a10dfc3980190140b37'}}


def sequence_recipe(report):
    """Recognize only the independently reviewed constant native chart recipe."""
    if report.get("source", {}).get("path") != SEQUENCE_SOURCE:
        return False
    expected = {"template": SEQUENCE_SOURCE, "expansions": [], "slots": {}}
    if (report.get("source") != {"path": SEQUENCE_SOURCE, "sha256": SEQUENCE_SHA}
        or report.get("output") != SEQUENCE_OUTPUT or report.get("report_class") != "interactive"
        or report.get("recipe") != expected or report.get("reviewed_scripts") != [SEQUENCE_SCRIPT]
        or report.get("bootstrap_id") is not None or report.get("bootstrap_sha256") is not None
        or report.get("providers") != {} or report.get("reviewed_provider_origins") != []
        or report.get("provider_calls") != []):
        raise AdmissionError("native sequence recipe differs from its finite reviewed source")
    directory = SEQUENCE_OUTPUT.rsplit("/", 1)[0] + "/"
    resources = {directory + name: {"source": "docs/" + directory + name,
                 "kind": "native-sequence-data", **identity} for name, identity in SEQUENCE_FILES.items()}
    if report.get("resources") != resources:
        raise AdmissionError("native sequence data closure differs from its finite reviewed source")
    return True


def document_budget(repository, report, content, product_base):
    """An exact source-bound native allowance cannot admit nearby large documents."""
    selected_sequence = sequence_recipe(report)
    selected_nordic = len(content) > 524288 and report.get("source", {}).get("path") == NORDIC_SOURCE
    if selected_sequence or selected_nordic:
        try:
            origin = subprocess.check_output(["git", "-C", str(repository), "remote", "get-url", "origin"], text=True).strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise AdmissionError("native presentation requires its owned Git repository") from error
        if origin not in {"https://github.com/bijux/bijux-pollenomics.git", "git@github.com:bijux/bijux-pollenomics.git"}:
            raise AdmissionError("native presentation requires the reviewed Pollenomics repository")
    if selected_sequence:
        if product_base != SITE or len(content) != 9402 or digest(content) != SEQUENCE_SHA:
            raise AdmissionError("native sequence document differs from reviewed publication source")
    if len(content) <= 524288:
        return
    if (product_base != SITE or report.get("source") != {"path": NORDIC_SOURCE, "sha256": NORDIC_SHA}
        or report.get("output") != NORDIC_OUTPUT or len(content) != NORDIC_BYTES or digest(content) != NORDIC_SHA
        or report.get("reviewed_scripts") != [NORDIC_SCRIPT_SHA]
        or report.get("bootstrap_id") != "atlas-static-bootstrap"
        or report.get("bootstrap_sha256") != NORDIC_BOOTSTRAP_SHA
        or digest(canonical(report.get("recipe"))) != NORDIC_RECIPE_SHA
        or digest(canonical(report.get("resources"))) != NORDIC_RESOURCES_SHA):
        raise AdmissionError("report exceeds its reviewed document budget")
    for path, identity in NORDIC_PRODUCERS.items():
        if digest(read_owned(repository, path)) != identity:
            raise AdmissionError("native Nordic producer differs from its finite reviewed source")


def sequence_data(repository, report, output, resource, content, product_base):
    """Plain JSON is a capability of one original chart, never a generic resource."""
    if product_base != SITE or not sequence_recipe(report) or report["resources"].get(output) != resource:
        raise AdmissionError("plain native data requires its exact reviewed sequence recipe")
    if len(content) != resource["bytes"] or digest(content) != resource["sha256"]:
        raise AdmissionError("native sequence data differs from its finite reviewed bytes")
    parsed = json_data(content)
    inspect_data(parsed, product_base, report["output"])
    if output.endswith("/manifest.json"):
        expected = {name: identity["sha256"] for name, identity in SEQUENCE_FILES.items() if name != "manifest.json"}
        if (parsed.get("schema_version") != "swedish-native-pollen-sequences.v1"
            or parsed.get("files_sha256") != expected
            or [parsed.get(key) for key in ("sample_count", "observation_count", "control_count")] != [228, 5464, 46]):
            raise AdmissionError("native sequence manifest differs from retained source identities")
    return {"sha256": digest(content), "bytes": len(content), "scope": "retained-native-sequence-data"}


def bootstrap(document, report):
    """Only one exact reviewed source has a bootstrap-free executable recipe."""
    if sequence_recipe(report):
        if any(script["attrs"].get("type") in {"application/json", "application/ld+json"} for script in document.scripts):
            raise AdmissionError("native sequence source cannot acquire a serialized bootstrap")
        return
    scripts = [script for script in document.scripts if script["attrs"].get("id") == report["bootstrap_id"]]
    if (len(scripts) != 1 or scripts[0]["attrs"].get("type") != "application/json"
        or digest(canonical(json_data(scripts[0]["body"]))) != report["bootstrap_sha256"]):
        raise AdmissionError("interactive bootstrap differs from committed ownership")
