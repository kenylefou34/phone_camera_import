"""Interface en ligne de commande du trieur."""

import argparse
import logging
from pathlib import Path

from .catalog import Catalog
from .noise import clean_noise
from .sorter import sort_folder


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(
        prog="mediasort",
        description="Range des photos/vidéos dans une bibliothèque par date.",
    )
    parseur.add_argument("--source", required=True, type=Path, help="dossier source à trier")
    parseur.add_argument("--library", required=True, type=Path, help="bibliothèque cible")
    parseur.add_argument("--catalog", type=Path, default=Path("catalog.db"),
                         help="fichier du catalogue SQLite")
    parseur.add_argument("--dry-run", action="store_true", help="simulation : ne rien déplacer")
    parseur.add_argument("--seed", action="store_true",
                         help="amorcer le catalogue avant de trier")
    parseur.add_argument("--seed-from", type=Path, default=None,
                         help="dossier à indexer pour l'amorçage (défaut : toute la bibliothèque)")
    parseur.add_argument("--clean-noise", action="store_true",
                         help="supprimer le bruit résiduel après tri")
    parseur.add_argument("--verbose", action="store_true", help="journal détaillé")
    args = parseur.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")

    cat = Catalog(args.catalog)
    try:
        if args.seed:
            source_amorce = args.seed_from or args.library
            n = cat.seed_from_library(source_amorce,
                                      exclude=[args.source, args.library / "_A_TRIER"])
            print(f"Catalogue amorcé depuis {source_amorce} : {n} médias indexés.")

        report = sort_folder(args.source, args.library, cat, dry_run=args.dry_run)
        prefixe = "[SIMULATION] " if args.dry_run else ""
        print(f"{prefixe}Bilan : {report.sorted} rangés, {report.duplicates} doublons ignorés, "
              f"{report.to_triage} à trier, {report.skipped} exclus, {report.errors} erreurs.")

        if args.clean_noise:
            supprimes = clean_noise(args.source, dry_run=args.dry_run)
            verbe = "à supprimer" if args.dry_run else "supprimés"
            print(f"{prefixe}Bruit {verbe} : {len(supprimes)} fichiers.")
    finally:
        cat.close()
    return 0
