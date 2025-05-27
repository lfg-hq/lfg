"""
ai_utils.py  –  project-code I/O helpers (storage + Git-style patch logic)
"""

import json
import os
import random
import string
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any
from subprocess import CalledProcessError

from .ai_tools import read_file, write_file        # noqa – only for tool schemas
from projects.models import Project, ProjectCodeGeneration
from coding.docker.docker_utils import Sandbox

def run_command(command: str, project_id: int | str) -> str:
    """
    Run a command in the terminal.
    """
    sandbox = Sandbox(project_id)
    sandbox.start()
    print("\n\n\nCommand to run: ", command)
    result = sandbox.exec(command)
    print("\n\n\nResult: ", result)

    return {
        "success": True,
        "message": result,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Storage-folder helpers
# ──────────────────────────────────────────────────────────────────────────────
def get_project_storage_folder(project_id: int | str) -> str:
    """
    Lazily create (or fetch) the random storage folder for a project.
    Returns **just** the 16-char folder name.
    """
    if project_id is None:
        return {"is_notification": False,
                "message_to_agent": "Error: project_id is required to generate code"}

    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {"is_notification": False,
                "message_to_agent": f"Error: Project with ID {project_id} does not exist"}

    try:
        code_gen = ProjectCodeGeneration.objects.get(project=project)
    except ProjectCodeGeneration.DoesNotExist:
        folder_name = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
        base_dir = Path(__file__).resolve().parents[2] / "storage"
        (base_dir / folder_name).mkdir(parents=True, exist_ok=True)

        code_gen = ProjectCodeGeneration(project=project, folder_name=folder_name)
        code_gen.save()

    return code_gen.folder_name


# ──────────────────────────────────────────────────────────────────────────────
# File operations
# ──────────────────────────────────────────────────────────────────────────────
def read_file_from_storage(file_path: str, project_id: int | str) -> Dict[str, Any]:
    project_folder = get_project_storage_folder(project_id)
    base_dir = Path(__file__).resolve().parents[2] / "storage"
    full_path = base_dir / project_folder / file_path

    print(f"\n[read] {full_path}")

    if full_path.exists():
        try:
            return {"file_path": file_path, "content": full_path.read_text()}
        except Exception as exc:                                     # noqa: BLE001
            return {"error": f"Failed to read file: {exc}"}
    return {"not_found": f"The file {file_path} doesn't exist. Create it first."}


def write_files_to_storage(file_list: List[Dict[str, str]] | Dict[str, str] | str,
                           project_id: int | str) -> Dict[str, Any]:
    """
    Accepts:
        • [{file_path, source_code}, …]
        • {file_path, source_code}
        • JSON string of either form
    """
    # ── normalise input ───────────────────────────────────────────────────────
    if isinstance(file_list, str):
        file_list = json.loads(file_list)
    if isinstance(file_list, dict):
        file_list = [file_list]

    project_folder = get_project_storage_folder(project_id)
    base_dir = Path(__file__).resolve().parents[2] / "storage"
    files_written: list[str] = []

    print("\n[write_files] incoming payload →", file_list)

    for f in file_list:
        file_path = f["file_path"]
        source_code = f["source_code"]

        full_path = base_dir / project_folder / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        write_to_git_patch_mode(full_path, source_code)
        files_written.append(file_path)

    return {
        "success": True,
        "message": f"Generated {len(files_written)} files in project {project_id}",
        "files_written": files_written,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Git-style patch writer
# ──────────────────────────────────────────────────────────────────────────────
def write_to_git_patch_mode(file_path: str | Path, source_code: str) -> None:
    """
    Modified patch writer with better fallback handling for corrupt patches.
    """
    file_path = Path(file_path)
    parent_dir = file_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    
    # If it's not a patch format, just write it directly
    if not source_code.lstrip().startswith("diff --git"):
        file_path.write_text(source_code, encoding="utf-8")
        return
    
    # Handle new file case
    if "\n--- /dev/null" in source_code or source_code.splitlines()[1].endswith("/dev/null"):
        print("[patch] Detected /dev/null diff → treat as brand-new file")
        # Extract content (lines starting with +, excluding the +++ line)
        new_content = "\n".join(
            ln[1:] for ln in source_code.splitlines()
            if ln.startswith("+") and not ln.startswith("+++ ")
        )
        file_path.write_text(new_content, encoding="utf-8")
        return
    
    # For existing files, try applying the patch
    patch_path = parent_dir / f"{file_path.stem}.manual.patch"
    patch_path.write_text(source_code, encoding="utf-8")
    
    try:
        subprocess.run(
            ["git", "apply", "--ignore-space-change", patch_path.name],
            cwd=parent_dir,
            check=True,
        )
        print(f"[patch] Applied patch to {file_path.name}")
    except Exception as e:
        # If git apply fails, try to fix the patch format
        print(f"[patch] Git apply failed: {e}, trying to fix patch")
        fixed_patch = fix_patch_format(source_code, file_path)
        
        if fixed_patch:
            # Try again with fixed patch
            fixed_patch_path = parent_dir / f"{file_path.stem}.fixed.patch"
            fixed_patch_path.write_text(fixed_patch, encoding="utf-8")
            
            try:
                subprocess.run(
                    ["git", "apply", "--ignore-space-change", fixed_patch_path.name],
                    cwd=parent_dir,
                    check=True,
                )
                print(f"[patch] Applied fixed patch to {file_path.name}")
                fixed_patch_path.unlink(missing_ok=True)
                return
            except Exception as nested_e:
                print(f"[patch] Fixed patch still failed: {nested_e}")
                fixed_patch_path.unlink(missing_ok=True)
        
        # Last resort: extract just the content modifications
        if file_path.exists():
            # Read the current file
            current_content = file_path.read_text(encoding="utf-8")
            lines = current_content.splitlines()
            
            # Extract changes from the patch (very simplified)
            patch_lines = source_code.splitlines()
            section_start = None
            
            # Look for additions and try to apply them sensibly
            for i, line in enumerate(patch_lines):
                if line.startswith("@@"):
                    # Found a hunk header, extract line numbers
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            # Parse old start line number
                            old_start = int(parts[1].split(',')[0][1:])
                            section_start = old_start - 1  # 0-indexed
                        except:
                            section_start = None
                
                # If we know where to insert and this is an addition
                elif section_start is not None and line.startswith("+") and not line.startswith("+++ "):
                    if section_start < len(lines):
                        # Insert at appropriate position
                        lines.insert(section_start, line[1:])
                        section_start += 1
                    else:
                        # Append to the end
                        lines.append(line[1:])
            
            # Write the modified content back
            file_path.write_text("\n".join(lines), encoding="utf-8")
            print(f"[patch] Applied best-effort manual changes to {file_path.name}")
        else:
            # File doesn't exist but it should for a modification - create it with additions only
            print(f"[patch] File {file_path.name} doesn't exist, creating with additions only")
            new_content = "\n".join(
                ln[1:] for ln in source_code.splitlines()
                if ln.startswith("+") and not ln.startswith("+++ ")
            )
            file_path.write_text(new_content, encoding="utf-8")
    
    finally:
        # Clean up patch file
        patch_path.unlink(missing_ok=True)

def fix_patch_format(patch_content, file_path):
    """
    Attempt to fix common patch format issues.
    """
    lines = patch_content.splitlines()
    fixed_lines = []
    
    # Add proper file headers
    fixed_lines.append(f"diff --git a/{file_path.name} b/{file_path.name}")
    fixed_lines.append(f"--- a/{file_path.name}")
    fixed_lines.append(f"+++ b/{file_path.name}")
    
    # Find and fix hunk headers
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            # Make sure the header has proper context
            if not line.endswith("@@"):
                parts = line.split("@@")
                if len(parts) >= 2:
                    fixed_lines.append(f"{parts[0]}@@ {parts[1]} @@")
                else:
                    fixed_lines.append(f"{line} @@")
            else:
                fixed_lines.append(line)
        elif not (line.startswith("diff --git") or line.startswith("---") or line.startswith("+++")):
            # Add content lines
            fixed_lines.append(line)
        i += 1
    
    return "\n".join(fixed_lines)