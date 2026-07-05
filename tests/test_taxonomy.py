from pathlib import Path

from juara_station.taxonomy import resolve_taxon


def test_clements_taxonomy_resolves_non_heuristic_species():
    taxon = resolve_taxon("Hoatzin")

    assert taxon.genus == "Opisthocomus"
    assert taxon.family == "Opisthocomidae"
    assert taxon.order == "Opisthocomiformes"


def test_clements_taxonomy_resolves_from_species_list_scientific_name(tmp_path: Path):
    species_list = tmp_path / "species.txt"
    species_list.write_text("Opisthocomus hoazin_Local mystery call\n")

    taxon = resolve_taxon("Local mystery call", str(species_list))

    assert taxon.common_name == "Hoatzin"
    assert taxon.genus == "Opisthocomus"
    assert taxon.family == "Opisthocomidae"
    assert taxon.order == "Opisthocomiformes"
