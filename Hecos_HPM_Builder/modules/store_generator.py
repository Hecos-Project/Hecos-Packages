import os
import sys
import json
import hashlib
import zipfile
import datetime
import subprocess
import re
from colorama import Fore, Style
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print(f"{Fore.RED}Error: 'tomli' library is required to parse manifests.{Style.RESET_ALL}")
        sys.exit(1)

from pathlib import Path


def _detect_git_info(repo_dir: Path) -> tuple[str | None, str]:
    """Auto-detect GitHub owner/repo and active branch using git CLI if available."""
    github_repo = None
    branch = "main"
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        remote_url = res.stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+)/([^/\.]+?)(?:\.git)?$", remote_url)
        if m:
            github_repo = f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass

    try:
        res_br = subprocess.run(
            ["git", "-C", str(repo_dir), "branch", "--show-current"],
            capture_output=True, text=True, check=True
        )
        cur_br = res_br.stdout.strip()
        if cur_br:
            branch = cur_br
    except Exception:
        pass

    return github_repo, branch


def generate_store_catalog(
    repo_dir: str | Path | None = None,
    packages_dir: str | Path | None = None,
    sources_dir: str | Path | None = None,
    output_file: str | Path | None = None,
    github_repo: str | None = None,
    branch: str | None = None,
    interactive: bool = False,
):
    print(f"\n{Fore.CYAN}--- Store Catalog Generator ---{Style.RESET_ALL}")
    
    builder_dir = Path(__file__).resolve().parent.parent
    default_repo_dir = builder_dir.parent.resolve()
    
    if interactive and not repo_dir and not packages_dir:
        try:
            user_in = input(f"Target repository root [{default_repo_dir}]: ").strip()
            if user_in:
                repo_dir = Path(user_in).resolve()
        except Exception:
            pass

    if repo_dir:
        repo_dir = Path(repo_dir).resolve()
    elif packages_dir:
        repo_dir = Path(packages_dir).resolve().parent
    else:
        repo_dir = default_repo_dir

    if packages_dir:
        packages_path = Path(packages_dir).resolve()
    else:
        packages_path = (repo_dir / "packages").resolve()

    if sources_dir:
        sources_path = Path(sources_dir).resolve()
    else:
        sources_path = (repo_dir / "sources").resolve()

    if not packages_path.exists():
        print(f"{Fore.RED}Packages folder not found: {packages_path}{Style.RESET_ALL}")
        return

    # Auto-detect git info
    detected_gh, detected_branch = _detect_git_info(repo_dir)
    if not github_repo:
        github_repo = detected_gh
    if not branch:
        branch = detected_branch or "main"

    if not github_repo:
        if repo_dir.name.lower() == "hecos-packages":
            github_repo = "Hecos-Project/Hecos-Packages"
        else:
            github_repo = f"Hecos-Project/{repo_dir.name}"

    is_official_hecos = (github_repo.lower() == "hecos-project/hecos-packages")

    # Determine output destinations
    output_destinations: list[Path] = []
    if output_file:
        output_destinations.append(Path(output_file).resolve())
    else:
        # Standard store folder inside the repository
        store_dir = repo_dir / "store"
        store_dir.mkdir(parents=True, exist_ok=True)
        output_destinations.append(store_dir / "index.json")

        # Also write inside packages_path as a fallback
        output_destinations.append(packages_path / "index.json")

        # If official Hecos-Packages and Hecos-Website repo exists nearby, update it too
        website_store_dir = (repo_dir.parent / "Hecos-Website" / "store").resolve()
        if is_official_hecos and website_store_dir.exists():
            output_destinations.append(website_store_dir / "index.json")

    print(f"{Fore.WHITE}Repository Root : {repo_dir}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Packages Dir    : {packages_path}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}GitHub Repo     : {github_repo} ({branch}){Style.RESET_ALL}")
    print(f"{Fore.WHITE}Output Catalog  : {output_destinations[0]}{Style.RESET_ALL}")

    catalog_url = (
        "https://hecos-project.github.io/store/index.json"
        if is_official_hecos
        else f"https://raw.githubusercontent.com/{github_repo}/{branch}/store/index.json"
    )

    catalog_map = {}
    catalog = {
        "version": "1",
        "catalog_url": catalog_url,
        "generated_at": datetime.datetime.utcnow().isoformat()[:19] + "Z",
        "packages": []
    }
    
    hpkg_files = list(packages_path.rglob("*.hpkg"))
    if not hpkg_files:
        print(f"{Fore.YELLOW}No .hpkg files found in {packages_path}{Style.RESET_ALL}")
        return

    for filepath in hpkg_files:
        filename = filepath.name
        print(f"{Fore.LIGHTBLACK_EX}Analyzing {filename}...{Style.RESET_ALL}")
        
        # Hash and Size
        size = filepath.stat().st_size
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()
        
        # Read Manifest from zip
        manifest_data = None
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                for zname in zf.namelist():
                    if zname.endswith("hpkg_manifest.toml"):
                        manifest_content = zf.read(zname).decode("utf-8")
                        manifest_data = tomllib.loads(manifest_content)
                        break
        except Exception as e:
            print(f"{Fore.RED}Error reading {filename}: {e}{Style.RESET_ALL}")
            continue
            
        if not manifest_data:
            print(f"{Fore.RED}hpkg_manifest.toml not found in {filename}{Style.RESET_ALL}")
            continue
            
        pkg_id = manifest_data.get("id") or filename.split("-")[0]

        # Preview image logic
        PREVIEW_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        manifest_category = manifest_data.get("category")
        if not manifest_category and manifest_data.get("type"):
            manifest_category = manifest_data.get("type") + "s"
        pkg_category = manifest_category or filepath.parent.name
        
        BASE_RAW = f"https://raw.githubusercontent.com/{github_repo}/{branch}/sources/{pkg_category}/{pkg_id}_src"

        raw_screenshots = manifest_data.get("screenshots", [])
        screenshots = []
        if raw_screenshots:
            for s in raw_screenshots:
                # Rewrite legacy Hecos-Packages screenshot URLs if targeting a different repo
                if not is_official_hecos and "Hecos-Project/Hecos-Packages" in s:
                    s = s.replace("Hecos-Project/Hecos-Packages", github_repo)
                screenshots.append(s)
        else:
            try:
                with zipfile.ZipFile(filepath, "r") as zf:
                    names_lower = {n.lower(): n for n in zf.namelist()}

                    numbered = {}
                    for lower, orig in names_lower.items():
                        basename = lower.split("/")[-1]
                        if basename.startswith("preview_"):
                            stem, _, ext = basename.partition(".")
                            ext = "." + ext
                            if ext in PREVIEW_EXTS:
                                try:
                                    idx = int(stem.replace("preview_", ""))
                                    numbered[idx] = orig.split("/")[-1]
                                except ValueError:
                                    pass

                    if numbered:
                        screenshots = [
                            f"{BASE_RAW}/{fname}"
                            for _, fname in sorted(numbered.items())
                        ]
                    elif "preview.png" in names_lower:
                        screenshots = [f"{BASE_RAW}/preview.png"]
                    else:
                        screenshots = [f"https://raw.githubusercontent.com/{github_repo}/{branch}/Hecos_module_Image_preview.png"]
            except Exception:
                screenshots = [f"https://raw.githubusercontent.com/{github_repo}/{branch}/Hecos_module_Image_preview.png"]

        # Capabilities block
        cap = manifest_data.get("capabilities", {})
        capabilities = {
            "llm_tools":       cap.get("llm_tools", []),
            "slash_commands":  cap.get("slash_commands", []),
            "has_widget":      cap.get("has_widget", False),
            "has_config_panel": cap.get("has_config_panel", False),
            "has_api_routes":  cap.get("has_api_routes", False),
            "has_system_calls": cap.get("has_system_calls", False),
            "notes":           cap.get("notes", ""),
        }

        # Exact relative path inside packages directory
        try:
            rel_hpkg = filepath.relative_to(packages_path).as_posix()
        except ValueError:
            rel_hpkg = f"{pkg_category}/{filename}"

        download_url = f"https://raw.githubusercontent.com/{github_repo}/{branch}/packages/{rel_hpkg}"
        homepage = manifest_data.get(
            "homepage",
            f"https://hecos-project.github.io/store/#{pkg_id}" if is_official_hecos else f"https://github.com/{github_repo}#{pkg_id}"
        )

        pkg_entry = {
            "id": pkg_id,
            "name": manifest_data.get("name", "Unknown Package"),
            "type": manifest_data.get("type", "plugin"),
            "level": manifest_data.get("level", 5),
            "version": manifest_data.get("version", "1.0.0"),
            "author": manifest_data.get("author", "Unknown"),
            "description": manifest_data.get("description", ""),
            "tags": manifest_data.get("tags", []),
            "download_url": download_url,
            "size_bytes": size,
            "sha256": file_hash,
            "screenshots": screenshots,
            "changelog": manifest_data.get("changelog", "Automatic update generated by the Store Catalog Builder."),
            "homepage": homepage,
            "fa_icon": manifest_data.get("fa_icon", "fa-box"),
            "featured": manifest_data.get("featured", False),
            "capabilities": capabilities,
            "dependencies": manifest_data.get("dependencies", []),
            "pip_requirements": manifest_data.get("pip_requirements", []),
        }
        
        existing_pkg = catalog_map.get(pkg_id)
        if existing_pkg:
            def parse_ver(v_str):
                return [int(x) if x.isdigit() else 0 for x in v_str.replace('-', '.').split('.')]
            
            try:
                if parse_ver(pkg_entry["version"]) > parse_ver(existing_pkg["version"]):
                    catalog_map[pkg_id] = pkg_entry
                    print(f" {Fore.GREEN}[OK] Updated: {pkg_entry['name']} to v{pkg_entry['version']}{Style.RESET_ALL}")
            except Exception:
                if pkg_entry["version"] > existing_pkg["version"]:
                    catalog_map[pkg_id] = pkg_entry
                    print(f" {Fore.GREEN}[OK] Updated: {pkg_entry['name']} to v{pkg_entry['version']}{Style.RESET_ALL}")
        else:
            catalog_map[pkg_id] = pkg_entry
            print(f" {Fore.GREEN}[OK] Added: {pkg_entry['name']} v{pkg_entry['version']}{Style.RESET_ALL}")
        
    try:
        catalog["packages"] = list(catalog_map.values())
        for dest in output_destinations:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2, ensure_ascii=False)
            print(f"{Fore.GREEN}Catalog saved at: {dest}{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}Done! Total packages in catalog: {len(catalog['packages'])}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error saving the catalog: {e}{Style.RESET_ALL}")
