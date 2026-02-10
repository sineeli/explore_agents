"""
Metadata Loader — fetches environment-specific metadata from APIs at startup.

Nothing is hardcoded. On environment load:
  1. Fetch hierarchies for each dimension (ITEM, TIME, LOCATION) from the realm API
  2. Fetch members for each dimension
  3. Fetch measure definitions (measures, versions, derived versions)
  4. Build per-dimension JSON documents ready for vector store indexing

The 3 dimensions (ITEM, TIME, LOCATION) are the only constants.
Everything else — hierarchy levels, members, measures — comes from the API.
"""

import json
import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# The only fixed constants — dimension names
DIMENSIONS = ["ITEM", "TIME", "LOCATION"]


@dataclass
class DimensionMetadata:
    """Metadata for a single dimension, fetched from the realm API."""
    name: str                                  # ITEM, TIME, or LOCATION
    hierarchies: list[dict] = field(default_factory=list)  # raw hierarchy defs from API
    members: list[dict] = field(default_factory=list)      # member rows from API


@dataclass
class RealmMetadata:
    """All metadata for the current environment/realm."""
    dimensions: dict[str, DimensionMetadata] = field(default_factory=dict)
    measures: list[dict] = field(default_factory=list)      # measure definitions
    versions: list[dict] = field(default_factory=list)      # version definitions
    derived_versions: list[dict] = field(default_factory=list)  # derived version defs


class MetadataLoader:
    """
    Fetches metadata from the realm API and prepares vector store documents.

    In production, each method calls the real API.
    For local development, it falls back to JSON files in data/.
    """

    def __init__(self, api_base_url: str, use_local_fallback: bool = True):
        self.api_base_url = api_base_url
        self.use_local_fallback = use_local_fallback
        self._data_dir = Path(__file__).parent / "data"

    def load_all(self) -> RealmMetadata:
        """Fetch all metadata from the realm API and return a RealmMetadata object."""
        realm = RealmMetadata()

        # Load each dimension
        for dim_name in DIMENSIONS:
            dim = DimensionMetadata(name=dim_name)
            dim.hierarchies = self._fetch_hierarchies(dim_name)
            dim.members = self._fetch_members(dim_name)
            realm.dimensions[dim_name] = dim

        # Load measures
        measures_data = self._fetch_measures()
        realm.measures = measures_data.get("measures", [])
        realm.versions = measures_data.get("versions", [])
        realm.derived_versions = measures_data.get("derivedVersions", [])

        return realm

    # ------------------------------------------------------------------
    # API fetchers — swap these for real HTTP calls in production
    # ------------------------------------------------------------------

    def _fetch_hierarchies(self, dimension: str) -> list[dict]:
        """
        Fetch hierarchy definitions for a dimension.

        Production:
            GET {api_base_url}/metadata/dimensions/{dimension}/hierarchies
            Returns: list of hierarchy objects with levels
        """
        # ---- PRODUCTION ----
        # import requests
        # resp = requests.get(f"{self.api_base_url}/metadata/dimensions/{dimension}/hierarchies")
        # resp.raise_for_status()
        # return resp.json()

        # ---- LOCAL FALLBACK ----
        if self.use_local_fallback:
            data = self._load_local_json("hierarchies.json")
            for d in data.get("dimensions", []):
                if d["name"] == dimension:
                    return d.get("hierarchies", [])
        return []

    def _fetch_members(self, dimension: str) -> list[dict]:
        """
        Fetch member rows for a dimension.

        Production:
            GET {api_base_url}/metadata/dimensions/{dimension}/members
            Returns: list of member row dicts (normalized, all levels per row)
        """
        # ---- PRODUCTION ----
        # import requests
        # resp = requests.get(f"{self.api_base_url}/metadata/dimensions/{dimension}/members")
        # resp.raise_for_status()
        # return resp.json()

        # ---- LOCAL FALLBACK ----
        if self.use_local_fallback:
            data = self._load_local_json("members.json")
            key_map = {"ITEM": "itemMembers", "TIME": "timeMembers", "LOCATION": "locationMembers"}
            return data.get(key_map.get(dimension, ""), [])
        return []

    def _fetch_measures(self) -> dict:
        """
        Fetch measure, version, and derived version definitions.

        Production:
            GET {api_base_url}/metadata/measures
            Returns: {"measures": [...], "versions": [...], "derivedVersions": [...]}
        """
        # ---- PRODUCTION ----
        # import requests
        # resp = requests.get(f"{self.api_base_url}/metadata/measures")
        # resp.raise_for_status()
        # return resp.json()

        # ---- LOCAL FALLBACK ----
        if self.use_local_fallback:
            return self._load_local_json("measures.json")
        return {}

    def _load_local_json(self, filename: str) -> dict:
        path = self._data_dir / filename
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}


# ---------------------------------------------------------------------------
# Vector store document builders
# ---------------------------------------------------------------------------

def build_index_documents(realm: RealmMetadata) -> dict[str, bytes]:
    """
    Build JSON documents for each vector store index from the fetched metadata.

    Returns a dict: index_name -> JSON bytes (ready for upload).

    Indexes:
      - item_index: ITEM dimension hierarchies + members
      - time_index: TIME dimension hierarchies + members
      - location_index: LOCATION dimension hierarchies + members
      - measure_index: measures + versions + derived versions
    """
    docs = {}

    # Per-dimension indexes
    for dim_name in DIMENSIONS:
        dim = realm.dimensions.get(dim_name)
        if not dim:
            continue

        index_name = f"{dim_name.lower()}_index"

        # Build a rich document the model can search
        doc = {
            "indexType": "dimension",
            "dimension": dim_name,
            "description": f"Hierarchy definitions and member data for the {dim_name} dimension. "
                           f"Use this to resolve user's natural language to actual hierarchy levels and member names.",
            "hierarchies": [],
            "memberSamples": [],
            "allLevels": [],
        }

        # Process hierarchies — extract all levels with descriptions
        for h in dim.hierarchies:
            h_doc = {
                "name": h.get("name", ""),
                "displayName": h.get("displayName", ""),
                "description": h.get("description", ""),
                "levels": [],
            }
            for lv in h.get("levels", []):
                level_info = {
                    "level": lv.get("level", ""),
                    "order": lv.get("order", 0),
                    "displayName": lv.get("displayName", lv.get("level", "")),
                    "description": lv.get("description", ""),
                }
                h_doc["levels"].append(level_info)
                doc["allLevels"].append(lv.get("level", ""))
            doc["hierarchies"].append(h_doc)

        # Dedupe allLevels
        doc["allLevels"] = sorted(set(doc["allLevels"]))

        # Extract distinct members per level for the model to reference
        level_members: dict[str, set] = {}
        for row in dim.members:
            for key, val in row.items():
                if val and str(val).strip():
                    level_members.setdefault(key, set()).add(str(val))

        for level_name, members in sorted(level_members.items()):
            doc["memberSamples"].append({
                "level": level_name,
                "memberCount": len(members),
                "members": sorted(members),
            })

        docs[index_name] = json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")

    # Measure index
    measure_doc = {
        "indexType": "measure",
        "description": (
            "All available measures, versions, and derived versions for this environment. "
            "Use this to resolve user's natural language to the correct measure name and version name. "
            "The API key for a measure-version is: {measure_name}{version_name} concatenated."
        ),
        "measures": [],
        "versions": [],
        "derivedVersions": [],
        "combinedKeyExamples": [],
    }

    for m in realm.measures:
        measure_doc["measures"].append({
            "name": m.get("name", ""),
            "displayName": m.get("displayName", ""),
            "description": m.get("description", ""),
            "aliases": m.get("aliases", []),
        })

    for v in realm.versions:
        measure_doc["versions"].append({
            "name": v.get("name", ""),
            "displayName": v.get("displayName", ""),
            "description": v.get("description", ""),
        })

    for dv in realm.derived_versions:
        measure_doc["derivedVersions"].append({
            "name": dv.get("name", ""),
            "displayName": dv.get("displayName", ""),
            "description": dv.get("description", ""),
            "baseVersion": dv.get("baseVersion", ""),
            "compareVersion": dv.get("compareVersion", ""),
            "type": dv.get("type", ""),
        })

    # Generate combined key examples from actual data
    if realm.measures and realm.versions:
        for m in realm.measures[:3]:
            for v in realm.versions[:3]:
                key = f"{m['name']}{v['name']}"
                measure_doc["combinedKeyExamples"].append({
                    "key": key,
                    "meaning": f"{m.get('displayName', m['name'])} for {v.get('displayName', v['name'])}",
                })
        # Also add derived version examples
        for m in realm.measures[:2]:
            for dv in realm.derived_versions[:2]:
                key = f"{m['name']}{dv['name']}"
                measure_doc["combinedKeyExamples"].append({
                    "key": key,
                    "meaning": f"{m.get('displayName', m['name'])} {dv.get('displayName', dv['name'])}",
                })

    docs["measure_index"] = json.dumps(measure_doc, indent=2, ensure_ascii=False).encode("utf-8")

    return docs


def build_system_prompt_context(realm: RealmMetadata) -> str:
    """
    Build a dynamic system prompt section from the fetched metadata.

    This is injected into the assistant's instructions so the model knows
    what levels and measures exist in THIS environment without searching.
    """
    lines = []

    lines.append("## This environment's dimensions and hierarchy levels\n")
    for dim_name in DIMENSIONS:
        dim = realm.dimensions.get(dim_name)
        if not dim:
            continue
        lines.append(f"### {dim_name} dimension")
        for h in dim.hierarchies:
            level_names = [lv.get("level", "") for lv in sorted(h.get("levels", []), key=lambda x: x.get("order", 0))]
            lines.append(f"- **{h.get('displayName', h.get('name', ''))}**: {' → '.join(level_names)}")
        lines.append("")

    lines.append("## Available measures\n")
    for m in realm.measures:
        aliases = ", ".join(m.get("aliases", []))
        alias_str = f" (aliases: {aliases})" if aliases else ""
        lines.append(f"- **{m.get('displayName', m['name'])}** (`{m['name']}`){alias_str}: {m.get('description', '')}")

    lines.append("\n## Available versions\n")
    for v in realm.versions:
        lines.append(f"- **{v.get('displayName', v['name'])}** (`{v['name']}`): {v.get('description', '')}")

    if realm.derived_versions:
        lines.append("\n## Derived versions (variances)\n")
        for dv in realm.derived_versions:
            lines.append(
                f"- **{dv.get('displayName', dv['name'])}** (`{dv['name']}`): "
                f"{dv.get('description', '')} [{dv.get('baseVersion', '')} vs {dv.get('compareVersion', '')}]"
            )

    lines.append("\n## Measure-version key format")
    lines.append("Concatenate measure name + version name. Examples from this environment:")
    if realm.measures and realm.versions:
        m0 = realm.measures[0]
        for v in realm.versions[:4]:
            lines.append(f"- `{m0['name']}{v['name']}` = {m0.get('displayName', '')} {v.get('displayName', '')}")
        if realm.derived_versions:
            dv0 = realm.derived_versions[0]
            lines.append(f"- `{m0['name']}{dv0['name']}` = {m0.get('displayName', '')} {dv0.get('displayName', '')}")

    return "\n".join(lines)
