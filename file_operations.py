"""Batch audio transfers with exclusive destination creation (no overwrites)."""
from dataclasses import dataclass
from pathlib import Path
import shutil
import hashlib
import json
import os
import stat
import uuid


@dataclass
class Transfer:
    track_id: str
    source: Path
    destination: Path
    fingerprint: tuple[int, int]


def reject_links(path):
    """Reject symlinks and Windows reparse points, including ancestor junctions."""
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"不支持链接路径：{part}")
        if part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError(f"不支持重解析点：{part}")


def inventory(source):
    reject_links(source)
    entries = []
    paths = [source]
    while paths:
        path = paths.pop()
        reject_links(path)
        info = path.lstat()
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError(f"不支持特殊文件：{path}")
        directory = stat.S_ISDIR(info.st_mode)
        digest = None
        if directory:
            paths.extend(sorted(path.iterdir(), reverse=True))
        else:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        entries.append((str(path.relative_to(source)), directory, info.st_size,
                        info.st_mtime_ns, info.st_mode, info.st_dev, info.st_ino, digest))
    return tuple(entries)


@dataclass
class FolderTransfer:
    source: Path
    destination: Path
    selected_track_ids: list
    affected_track_ids: list
    snapshot: tuple

    def preview(self):
        return {"source": str(self.source), "destination": str(self.destination),
                "selected_track_ids": self.selected_track_ids,
                "affected_track_ids": self.affected_track_ids,
                "file_count": sum(not row[1] for row in self.snapshot),
                "directory_count": sum(row[1] for row in self.snapshot),
                "total_bytes": sum(row[2] for row in self.snapshot if not row[1])}


def plan_folders(tracks, source_root, target_folder, keep_structure, registry):
    target = Path(target_folder)
    if not target.is_absolute():
        raise ValueError("目标文件夹必须是完整路径。")
    reject_links(target)
    target = target.resolve()
    if target.exists() and not target.is_dir():
        raise ValueError("目标路径不是文件夹。")
    roots = sorted({path.parent for _, path, _ in tracks}, key=lambda p: (len(p.parts), str(p)))
    sources = []
    for source in roots:
        reject_links(source)
        if source == source_root or not source.is_relative_to(source_root):
            raise ValueError("整目录范围触及扫描根或越界，请选择专辑子目录。")
        if not any(source.is_relative_to(parent) for parent in sources):
            sources.append(source)
    plans, destinations = [], set()
    for source in sources:
        destination = target / (source.relative_to(source_root) if keep_structure else source.name)
        reject_links(destination)
        if any(destination.is_relative_to(p) or p.is_relative_to(destination) for p in sources):
            raise ValueError("源目录与目标目录不能重叠。")
        if destination in destinations or destination.exists():
            raise FileExistsError(f"目标已存在或重复：{destination}")
        destinations.add(destination)
        plans.append(FolderTransfer(source, destination,
                     [key for key, path, _ in tracks if path.is_relative_to(source)],
                     [key for key, path in registry.items() if path.is_relative_to(source)],
                     inventory(source)))
    return target, plans


def actual_paths(root):
    if not root.exists():
        return []
    return [str(root), *(str(p) for p in sorted(root.rglob("*")))]


def execute_folders(plans, operation):
    results = []
    for plan in plans:
        result = {**plan.preview(), "status": "error", "error": None,
                  "remaining_sources": [], "residual_targets": []}
        created = False
        complete = False
        journal = None
        try:
            reject_links(plan.destination)
            if inventory(plan.source) != plan.snapshot:
                raise ValueError("源目录已变化，请重新预览。")
            plan.destination.parent.mkdir(parents=True, exist_ok=True)
            # A durable recovery record precedes all destination writes. It is
            # retained on failures and abrupt process termination.
            journal = plan.destination.parent / f".lossless-lens-transfer-{uuid.uuid4().hex}.json"
            with journal.open("x", encoding="utf-8") as stream:
                json.dump({"source": str(plan.source), "destination": str(plan.destination),
                           "operation": operation, "phase": "incomplete; inspect source and destination",
                           "source_manifest": plan.snapshot}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            plan.destination.mkdir()  # atomic reservation, never merge
            created = True
            for relative, directory, *_ in plan.snapshot:
                source, destination = plan.source / relative, plan.destination / relative
                reject_links(source)
                reject_links(destination)
                if directory:
                    if relative != ".":
                        destination.mkdir()
                else:
                    with source.open("rb") as incoming, destination.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
                        outgoing.flush()
                        os.fsync(outgoing.fileno())
                    shutil.copystat(source, destination)
            for relative, directory, *_ in reversed(plan.snapshot):
                if directory:
                    shutil.copystat(plan.source / relative, plan.destination / relative)
            if inventory(plan.source) != plan.snapshot:
                raise ValueError("源目录在复制期间变化，已保留源，请重新预览。")
            # Verify bytes as well as successful writes before deleting anything.
            for row in plan.snapshot:
                if not row[1]:
                    with (plan.destination / row[0]).open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != row[-1]:
                            raise ValueError("目标内容校验失败，源已保留。")
            complete = True
            if operation == "move":
                for row in reversed(plan.snapshot):
                    source = plan.source / row[0]
                    reject_links(source)
                    if row[1]:
                        source.rmdir()
                    else:
                        # Do not delete a file changed after the copy verification.
                        current = inventory(source)[0]
                        if current[1:] != row[1:]:
                            raise ValueError(f"源文件已变化，保留：{source}")
                        source.unlink()
            result["status"] = "moved" if operation == "move" else "copied"
            journal.unlink()
            journal = None
        except (OSError, ValueError, KeyboardInterrupt, SystemExit) as exc:
            result["status"] = "copied_not_removed" if complete else "error"
            result["error"] = f"{type(exc).__name__}: {exc}"
        result["remaining_sources"] = actual_paths(plan.source)
        result["residual_targets"] = actual_paths(plan.destination) if created and result["error"] else []
        if journal is not None and journal.exists():
            result["residual_targets"].append(str(journal))
            result["error"] = (result["error"] or "") + f"；恢复清单：{journal}"
        results.append(result)
    return results


def plan_transfers(tracks, source_root: Path, target_folder: str, keep_structure: bool):
    target = Path(target_folder)
    if not target.is_absolute():
        raise ValueError("目标文件夹必须是完整路径（盘符路径或 UNC 路径）。")
    reject_links(target)
    target = target.resolve()
    if target.exists() and not target.is_dir():
        raise ValueError("目标路径不是文件夹。")
    plans, destinations = [], set()
    for track_id, source, fingerprint in tracks:
        reject_links(source)
        try:
            relative = source.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"曲目不在本次扫描根目录内：{source.name}") from exc
        destination = (target / (relative if keep_structure else source.name)).resolve()
        reject_links(destination)
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
            reject_links(plan.source)
            reject_links(plan.destination)
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
