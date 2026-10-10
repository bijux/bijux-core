"""Canonical source YAML admission using the explicit manifest-capture prerequisite."""
from __future__ import annotations

_YAML_DOCUMENT_PARSER = r'''
require "yaml"
require "json"
text = STDIN.read
stream = YAML.parse_stream(text)
raise "one workflow document required" unless stream.children.length == 1
node = stream.children.first.root
value = YAML.safe_load(text, aliases: false)
def restore_keys(node, value)
  case node
  when Psych::Nodes::Mapping
    raise "ambiguous or duplicate YAML mapping" unless value.is_a?(Hash) && node.children.length == value.length * 2
    result = {}
    node.children.each_slice(2).with_index do |(key, child), index|
      raise "workflow mapping key must be scalar" unless key.is_a?(Psych::Nodes::Scalar)
      raise "duplicate workflow mapping key" if result.key?(key.value)
      result[key.value] = restore_keys(child, value.values[index])
    end
    result
  when Psych::Nodes::Sequence
    raise "ambiguous YAML sequence" unless value.is_a?(Array) && node.children.length == value.length
    node.children.each_with_index.map { |child, index| restore_keys(child, value[index]) }
  when Psych::Nodes::Scalar
    value
  else
    raise "unsupported YAML node"
  end
end
puts JSON.generate(restore_keys(node, value))
'''


def parse_workflow(content: bytes, label: str) -> dict:
    """Use the canonical Ruby YAML tool while preserving actual scalar mapping keys."""
    import json
    import subprocess

    try:
        result = subprocess.run(
            ["ruby", "-e", _YAML_DOCUMENT_PARSER],
            input=content.decode("utf-8"), text=True, capture_output=True, check=True,
        )
        document = json.loads(result.stdout)
    except FileNotFoundError as error:
        raise RuntimeError("ruby is required to parse canonical workflow projection") from error
    except (subprocess.CalledProcessError, UnicodeError, ValueError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise ValueError(f"unsupported workflow YAML {label}: {detail}") from error
    if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
        raise ValueError(f"{label} must be a workflow object with jobs")
    return document
