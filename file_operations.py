"""Batch audio transfers with exclusive destination creation (no overwrites)."""
from dataclasses import dataclass
from pathlib import Path
import shutil


@dataclass
class Transfer:
    track_id: str
    source: Path
    destination: Path
    fingerprint: tuple[int, int]


def plan_transfers(tracks, source_root: Path, target_folder: str, keep_structure: bool):
    target = Path(target_folder)
    if not target.is_absolute():
        raise ValueError("目标文件夹必须是完整路径（盘符路径或 UNC 路径）。")
    target = target.resolve()
    if target.exists() and not target.is_dir():
        raise ValueError("目标路径不是文件夹。")
    plans, destinations = [], set()
    for track_id, source, fingerprint in tracks:
        try:
            relative = source.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"曲目不在本次扫描根目录内：{source.name}") from exc
        destination = (target / (relative if keep_structure else source.name)).resolve()
        if not destination.is_relative_to(target):
            raise ValueError(f"目标子目录指向目标文件夹之外：{relative}")
        if destination in destinations:
            raise FileExistsError(f"多首曲目具有相同目标路径：{destination}。请保留目录结构或更换目标。")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"目标已存在，未执行任何文件操作：{destination}")
        destinations.add(destination)
        plans.append(Transfer(track_id, source, destination, fingerprint))
    return target, plans


def execute_transfers(plans, operation):
    results = []
    for plan in plans:
        result = {"id": plan.track_id, "name": plan.source.name,
                  "source": str(plan.source), "destination": str(plan.destination)}
        created = False
        try:
            plan.destination.parent.mkdir(parents=True, exist_ok=True)
            with plan.source.open("rb") as source:
                # Exclusive creation also prevents an overwrite if a target
                # appears after the batch's conflict check.
                with plan.destination.open("xb") as destination:
                    created = True
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
            after = plan.source.stat()
            if (after.st_size, after.st_mtime_ns) != plan.fingerprint:
                raise ValueError("源文件在处理过程中发生变化，已保留源文件，请重新分析。")
            shutil.copystat(plan.source, plan.destination)
        except (OSError, ValueError) as exc:
            detail = str(exc)
            if created:
                try:
                    plan.destination.unlink()
                except OSError as cleanup:
                    detail += f"；无法清理未完成的目标文件：{cleanup}"
            results.append({**result, "status": "error", "error": detail})
            continue
        if operation == "move":
            # Copy then unlink also works across disks and UNC shares. Never
            # remove the source until the complete copy and metadata succeed.
            try:
                plan.source.unlink()
            except OSError as exc:
                results.append({**result, "status": "copied_not_removed",
                                "error": f"已复制，但无法删除源文件：{exc}"})
                continue
        results.append({**result, "status": "moved" if operation == "move" else "copied", "error": None})
    return results
