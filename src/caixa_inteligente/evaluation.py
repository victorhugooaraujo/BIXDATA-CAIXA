"""Keep known-product accuracy and unknown false acceptances separate."""


def recognition_metrics(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("Avaliação sem consultas.")
    known = [row for row in rows if row["is_known"]]
    unknown = [row for row in rows if not row["is_known"]]
    accepted = [row for row in rows if row["accepted"] is not None]
    correct = sum(row["is_known"] and row["accepted"] == row["expected"] for row in accepted)
    false_unknown = sum(row["accepted"] is not None for row in unknown)
    return {
        "images": len(rows),
        "known_images": len(known),
        "unknown_images": len(unknown),
        "known_top1_accuracy": {
            mode: (
                sum(row[f"{mode}_prediction"] == row["expected"] for row in known) / len(known)
                if known
                else None
            )
            for mode in ("visual", "text", "hybrid")
        },
        "visual_baseline_gate": {
            "accepted": len(accepted),
            "accepted_correct": correct,
            "accepted_wrong": len(accepted) - correct,
            "precision_on_accepted": correct / len(accepted) if accepted else None,
            "coverage": len(accepted) / len(rows),
            "unknown_false_acceptances": false_unknown,
            "unknown_false_acceptance_rate": false_unknown / len(unknown) if unknown else None,
            "known_rejected": sum(row["accepted"] is None for row in known),
        },
        "hybrid_automatic_acceptance": False,
        "hybrid_rejection_discrimination_validated": False,
    }
