import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from caixa_inteligente.catalog import find_product, import_catalog, init_catalog
from caixa_inteligente.config import database_engine


def image_samples(directory: Path) -> list[tuple[str, Path]]:
    if not directory.is_dir():
        raise ValueError(f"Pasta de imagens não encontrada: {directory}")
    samples = [
        (folder.name, path)
        for folder in sorted(directory.iterdir())
        if folder.is_dir()
        for path in sorted(folder.iterdir())
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    if not samples:
        raise ValueError(f"Nenhuma imagem em {directory}/<sku>/imagem.jpg.")
    return samples


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Caixa inteligente — um produto por imagem.")
    commands = root.add_subparsers(dest="command", required=True)
    download = commands.add_parser(
        "dataset-download", help="Baixar subset do Grocery Store Dataset"
    )
    download.add_argument("--output", type=Path, default=Path("data/grocery"))
    download.add_argument("--classes", type=int, nargs="+", default=[6, 16, 63])
    download.add_argument("--train-per-class", type=int, default=10)
    download.add_argument("--eval-per-class", type=int, default=5)
    rpc = commands.add_parser("dataset-rpc", help="Instalar subset RPC com 200 produtos")
    rpc.add_argument("--output", type=Path, default=Path("data/rpc"))
    rpc.add_argument("--cache", type=Path, default=Path(".cache/rpc"))
    rpc.add_argument("--train-per-class", type=int, default=12)
    rpc.add_argument("--eval-per-class", type=int, default=4)
    rpc.add_argument("--workers", type=int, default=8)
    rpc.add_argument("--seed", type=int, default=42)
    rpc.add_argument("--source", choices=["huggingface", "kaggle"], default="huggingface")
    commands.add_parser("init-db", help="Criar tabelas no MySQL")
    catalog = commands.add_parser("catalog-import", help="Cadastrar/atualizar SKUs e preços CSV")
    catalog.add_argument("csv", type=Path)
    index = commands.add_parser("index", help="Extrair embeddings somente das imagens de treino")
    index.add_argument(
        "--images",
        type=Path,
        nargs="+",
        default=[Path("data/grocery/train")],
        help="Uma ou mais pastas de treino, com subpastas por SKU",
    )
    index.add_argument("--gallery", type=Path, default=Path("artifacts/gallery.npz"))
    index.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    for name in ["recognize", "evaluate"]:
        command = commands.add_parser(name)
        if name == "recognize":
            command.add_argument("image", type=Path)
        else:
            command.add_argument("--images", type=Path, default=Path("data/grocery/test"))
        command.add_argument("--gallery", type=Path, default=Path("artifacts/gallery.npz"))
        command.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
        command.add_argument("--min-similarity", type=float, default=0.75)
        command.add_argument("--min-margin", type=float, default=0.05)
    return root


def run(args: argparse.Namespace) -> dict:
    if args.command == "dataset-rpc":
        from caixa_inteligente.rpc_dataset import download_rpc_subset

        return download_rpc_subset(
            args.output,
            cache_dir=args.cache,
            train_per_class=args.train_per_class,
            eval_per_class=args.eval_per_class,
            workers=args.workers,
            seed=args.seed,
            source=args.source,
            progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
    if args.command == "dataset-download":
        from caixa_inteligente.dataset import download_grocery_subset

        return download_grocery_subset(
            args.output,
            class_ids=tuple(args.classes),
            max_train_per_class=args.train_per_class,
            max_eval_per_class=args.eval_per_class,
        )
    if args.command in {"init-db", "catalog-import"}:
        engine = database_engine()
        try:
            if args.command == "init-db":
                init_catalog(engine)
                return {"status": "created"}
            return {"imported": import_catalog(engine, args.csv)}
        finally:
            engine.dispose()

    from caixa_inteligente.vision import DinoV2Encoder, Gallery

    encoder = DinoV2Encoder(device=args.device)
    if args.command == "index":
        samples = [sample for directory in args.images for sample in image_samples(directory)]
        gallery = Gallery.build(samples, encoder)
        gallery.save(args.gallery)
        return {"gallery": str(args.gallery), "images": len(samples)}

    gallery = Gallery.load(args.gallery, expected_signature=encoder.signature)
    if args.command == "recognize":
        result = gallery.recognize(encoder.encode(args.image), args.min_similarity, args.min_margin)
        output = asdict(result)
        output["product"] = None
        if result.sku:
            engine = database_engine()
            try:
                product = find_product(engine, result.sku)
            finally:
                engine.dispose()
            if product is None:
                output.update(sku=None, reason="product_not_in_catalog")
            else:
                output["product"] = {
                    "sku": product.sku,
                    "name": product.name,
                    "unit_price_brl": str(product.price),
                }
        output["requires_review"] = output["sku"] is None
        return output

    samples = image_samples(args.images)
    accepted = correct = top1_correct = 0
    for expected, path in samples:
        result = gallery.recognize(encoder.encode(path), args.min_similarity, args.min_margin)
        top1_correct += bool(result.candidates and result.candidates[0].sku == expected)
        accepted += result.sku is not None
        correct += result.sku == expected
    return {
        "images": len(samples),
        "top1_accuracy": top1_correct / len(samples),
        "accepted": accepted,
        "requires_review": len(samples) - accepted,
        "coverage": accepted / len(samples),
        "accuracy_on_accepted": correct / accepted if accepted else None,
        "note": "Similaridade não é probabilidade; limiares precisam de calibração no val.",
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    load_dotenv()
    try:
        result = run(args)
    except SQLAlchemyError:
        print("Erro de banco: verifique MySQL, DATABASE_URL e execute init-db.", file=sys.stderr)
        return 1
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
