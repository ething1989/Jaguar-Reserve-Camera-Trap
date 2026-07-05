from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re


@dataclass(frozen=True)
class BirdTaxon:
    common_name: str
    scientific_name: str | None = None
    genus: str | None = None
    family: str | None = None
    order: str | None = None
    group: str | None = None


RANKS = ("genus", "family", "order", "group")


COMMON_GROUP_RULES: tuple[tuple[tuple[str, ...], str, str | None, str | None], ...] = (
    (("macaw",), "macaw", "Psittacidae", "Psittaciformes"),
    (("parrot", "parakeet", "amazon"), "parrot/parakeet", "Psittacidae", "Psittaciformes"),
    (("woodpecker", "flicker", "piculet"), "woodpecker", "Picidae", "Piciformes"),
    (("owl", "owlet"), "owl", "Strigidae", "Strigiformes"),
    (("nightjar", "nighthawk", "pauraque", "potoo"), "nightjar/potoo", "Caprimulgidae", "Caprimulgiformes"),
    (("heron", "egret", "bittern"), "heron/egret", "Ardeidae", "Pelecaniformes"),
    (("ibis", "spoonbill"), "ibis/spoonbill", "Threskiornithidae", "Pelecaniformes"),
    (("chachalaca", "guan", "curassow"), "chachalaca/guan/curassow", "Cracidae", "Galliformes"),
    (("tinamou",), "tinamou", "Tinamidae", "Tinamiformes"),
    (("hummingbird", "hermit", "mango", "sapphire", "emerald"), "hummingbird", "Trochilidae", "Apodiformes"),
    (("trogon",), "trogon", "Trogonidae", "Trogoniformes"),
    (("motmot",), "motmot", "Momotidae", "Coraciiformes"),
    (("kingfisher",), "kingfisher", "Alcedinidae", "Coraciiformes"),
    (("toucan", "aracari"), "toucan/aracari", "Ramphastidae", "Piciformes"),
    (("jacamar",), "jacamar", "Galbulidae", "Piciformes"),
    (("puffbird", "nunbird", "nunlet"), "puffbird/nunbird", "Bucconidae", "Piciformes"),
    (("antbird", "antwren", "antshrike", "antvireo", "fire-eye"), "antbird", "Thamnophilidae", "Passeriformes"),
    (("woodcreeper",), "woodcreeper", "Dendrocolaptidae", "Passeriformes"),
    (("hornero", "spinetail", "foliage-gleaner", "thornbird", "xenops"), "ovenbird/woodcreeper", "Furnariidae", "Passeriformes"),
    (("flycatcher", "tody-flycatcher", "tyrant", "elaenia", "pewee", "kingbird", "kiskadee"), "flycatcher", "Tyrannidae", "Passeriformes"),
    (("manakin",), "manakin", "Pipridae", "Passeriformes"),
    (("cotinga", "becard", "tityra"), "cotinga/tityra", "Cotingidae", "Passeriformes"),
    (("vireo", "greenlet", "peppershrike"), "vireo/peppershrike", "Vireonidae", "Passeriformes"),
    (("wren",), "wren", "Troglodytidae", "Passeriformes"),
    (("thrush", "solitaire"), "thrush", "Turdidae", "Passeriformes"),
    (("tanager", "dacnis", "honeycreeper", "saltator", "seedeater", "grassquit"), "tanager/finch", "Thraupidae", "Passeriformes"),
    (("oriole", "cacique", "oropendola", "cowbird", "blackbird"), "icterid", "Icteridae", "Passeriformes"),
    (("warbler", "redstart", "waterthrush"), "warbler", "Parulidae", "Passeriformes"),
    (("sparrow", "finch", "euphonia"), "sparrow/finch", None, "Passeriformes"),
    (("crow", "jay"), "crow/jay", "Corvidae", "Passeriformes"),
    (("hawk", "eagle", "kite", "harrier"), "hawk/eagle/kite", "Accipitridae", "Accipitriformes"),
    (("falcon", "caracara"), "falcon/caracara", "Falconidae", "Falconiformes"),
    (("vulture",), "vulture", None, None),
    (("sandpiper", "yellowlegs", "snipe", "dowitcher"), "shorebird", "Scolopacidae", "Charadriiformes"),
    (("plover", "lapwing"), "shorebird", "Charadriidae", "Charadriiformes"),
    (("gull", "tern", "skimmer"), "gull/tern/skimmer", "Laridae", "Charadriiformes"),
    (("duck", "teal", "wigeon", "screamer"), "waterfowl", "Anatidae", "Anseriformes"),
    (("dove", "pigeon"), "dove/pigeon", "Columbidae", "Columbiformes"),
    (("cuckoo", "ani"), "cuckoo/ani", "Cuculidae", "Cuculiformes"),
    (("rail", "gallinule", "coot", "crake"), "rail/gallinule", "Rallidae", "Gruiformes"),
)


FAMILY_ORDER_HINTS = {
    "Psittacidae": "Psittaciformes",
    "Picidae": "Piciformes",
    "Strigidae": "Strigiformes",
    "Caprimulgidae": "Caprimulgiformes",
    "Ardeidae": "Pelecaniformes",
    "Threskiornithidae": "Pelecaniformes",
    "Cracidae": "Galliformes",
    "Tinamidae": "Tinamiformes",
    "Trochilidae": "Apodiformes",
    "Trogonidae": "Trogoniformes",
    "Momotidae": "Coraciiformes",
    "Alcedinidae": "Coraciiformes",
    "Ramphastidae": "Piciformes",
    "Galbulidae": "Piciformes",
    "Bucconidae": "Piciformes",
    "Thamnophilidae": "Passeriformes",
    "Dendrocolaptidae": "Passeriformes",
    "Furnariidae": "Passeriformes",
    "Tyrannidae": "Passeriformes",
    "Pipridae": "Passeriformes",
    "Cotingidae": "Passeriformes",
    "Vireonidae": "Passeriformes",
    "Troglodytidae": "Passeriformes",
    "Turdidae": "Passeriformes",
    "Thraupidae": "Passeriformes",
    "Icteridae": "Passeriformes",
    "Parulidae": "Passeriformes",
    "Corvidae": "Passeriformes",
    "Accipitridae": "Accipitriformes",
    "Falconidae": "Falconiformes",
    "Scolopacidae": "Charadriiformes",
    "Charadriidae": "Charadriiformes",
    "Laridae": "Charadriiformes",
    "Anatidae": "Anseriformes",
    "Columbidae": "Columbiformes",
    "Cuculidae": "Cuculiformes",
    "Rallidae": "Gruiformes",
}


def normalize_common_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("_", " ").strip()).casefold()


@lru_cache(maxsize=16)
def load_species_taxa(species_list_path: str | None) -> dict[str, BirdTaxon]:
    if not species_list_path:
        return {}
    path = Path(species_list_path).expanduser()
    if not path.exists():
        return {}
    taxa: dict[str, BirdTaxon] = {}
    for line in path.read_text(errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        scientific_name: str | None = None
        common_name = text
        if "_" in text:
            scientific_name, common_name = (part.strip() for part in text.split("_", 1))
        genus = scientific_name.split()[0] if scientific_name and " " in scientific_name else None
        inferred = infer_taxon_from_common_name(common_name)
        taxon = BirdTaxon(
            common_name=common_name,
            scientific_name=scientific_name,
            genus=genus,
            family=inferred.family,
            order=inferred.order,
            group=inferred.group,
        )
        taxa[normalize_common_name(common_name)] = taxon
    return taxa


def resolve_taxon(common_name: str, species_list_path: str | None = None) -> BirdTaxon:
    taxa = load_species_taxa(str(species_list_path) if species_list_path else None)
    key = normalize_common_name(common_name)
    if key in taxa:
        return taxa[key]
    inferred = infer_taxon_from_common_name(common_name)
    return BirdTaxon(
        common_name=common_name,
        genus=inferred.genus,
        family=inferred.family,
        order=inferred.order,
        group=inferred.group,
    )


def infer_taxon_from_common_name(common_name: str) -> BirdTaxon:
    key = normalize_common_name(common_name)
    for terms, group, family, order in COMMON_GROUP_RULES:
        if any(term in key for term in terms):
            return BirdTaxon(
                common_name=common_name,
                family=family,
                order=order or (FAMILY_ORDER_HINTS.get(family) if family else None),
                group=group,
            )
    return BirdTaxon(common_name=common_name)


def taxon_rank_value(taxon: BirdTaxon, rank: str) -> str | None:
    value = getattr(taxon, rank, None)
    return value if isinstance(value, str) and value else None
