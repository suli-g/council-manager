import tempfile
import json
import pytest
import argparse
from pathlib import Path
from council_manager.cli import cmd_register_skill

def test_cmd_register_skill_no_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        args = argparse.Namespace(workspace=str(workspace))
        
        with pytest.raises(SystemExit) as exc_info:
            cmd_register_skill(args)
        assert exc_info.value.code == 1

def test_cmd_register_skill_no_skill_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        agents_dir = workspace / ".agents"
        agents_dir.mkdir(parents=True)
        
        args = argparse.Namespace(workspace=str(workspace))
        
        with pytest.raises(SystemExit) as exc_info:
            cmd_register_skill(args)
        assert exc_info.value.code == 1

def test_cmd_register_skill_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        agents_dir = workspace / ".agents"
        skill_dir = agents_dir / "skills" / "council-manager"
        skill_dir.mkdir(parents=True)
        
        skill_md = skill_dir / "SKILL.md"
        with open(skill_md, "w", encoding="utf-8") as f:
            f.write("test skill content")
            
        args = argparse.Namespace(workspace=str(workspace))
        
        # Call the command
        cmd_register_skill(args)
        
        # Verify skills.json was created
        skills_json = agents_dir / "skills.json"
        assert skills_json.exists()
        
        with open(skills_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        assert "entries" in data
        assert len(data["entries"]) == 1
        assert data["entries"][0]["path"] == str(skill_dir.as_posix())
