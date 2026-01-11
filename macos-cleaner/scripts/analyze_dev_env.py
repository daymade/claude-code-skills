#!/usr/bin/env python3
"""
Analyze development environment and find cleanable resources.

Checks:
- Docker (images, containers, volumes, build cache)
- Homebrew cache
- npm cache
- pip cache
- Old .git directories in archived projects

Usage:
    python3 analyze_dev_env.py
"""

import os
import sys
import subprocess
import json
from pathlib import Path


def format_size(bytes_size):
    """Convert bytes to human-readable format."""
    if bytes_size is None:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def run_command(cmd):
    """Run command and return output, or None if error."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_dir_size(path):
    """Get directory size using du command."""
    output = run_command(['du', '-sk', path])
    if output:
        try:
            size_kb = int(output.split()[0])
            return size_kb * 1024  # Convert to bytes
        except (ValueError, IndexError):
            pass
    return 0


def check_docker():
    """Check Docker resources."""
    print("\n🐳 Docker Resources")
    print("=" * 50)

    # Check if Docker is installed
    if not run_command(['which', 'docker']):
        print("   Docker not installed or not in PATH")
        return 0

    # Check if Docker daemon is running
    if not run_command(['docker', 'info']):
        print("   Docker daemon not running")
        return 0

    total_size = 0

    # Images
    images_output = run_command(['docker', 'images', '-q'])
    if images_output:
        image_count = len(images_output.split('\n'))
        print(f"\n📦 Images: {image_count}")

        # Get size estimate
        system_output = run_command(['docker', 'system', 'df', '--format', '{{json .}}'])
        if system_output:
            for line in system_output.split('\n'):
                try:
                    data = json.loads(line)
                    if data.get('Type') == 'Images':
                        size_str = data.get('Size', '')
                        # Parse size (format like "1.2GB")
                        if 'GB' in size_str:
                            size = float(size_str.replace('GB', '')) * 1024 * 1024 * 1024
                        elif 'MB' in size_str:
                            size = float(size_str.replace('MB', '')) * 1024 * 1024
                        else:
                            size = 0
                        print(f"   Total size: {format_size(size)}")
                        total_size += size
                except (json.JSONDecodeError, ValueError):
                    pass

    # Containers
    containers_output = run_command(['docker', 'ps', '-a', '-q'])
    if containers_output:
        container_count = len(containers_output.split('\n'))
        stopped = run_command(['docker', 'ps', '-a', '-f', 'status=exited', '-q'])
        stopped_count = len(stopped.split('\n')) if stopped else 0
        print(f"\n📦 Containers: {container_count} total, {stopped_count} stopped")

    # Volumes
    volumes_output = run_command(['docker', 'volume', 'ls', '-q'])
    if volumes_output:
        volume_count = len(volumes_output.split('\n'))
        print(f"\n📦 Volumes: {volume_count}")

        # List volumes
        for volume in volumes_output.split('\n')[:5]:  # Show first 5
            inspect = run_command(['docker', 'volume', 'inspect', volume])
            print(f"   - {volume}")
        if volume_count > 5:
            print(f"   ... and {volume_count - 5} more")

    # Build cache
    buildx_output = run_command(['docker', 'buildx', 'du'])
    if buildx_output and 'Total:' in buildx_output:
        print(f"\n📦 Build Cache:")
        for line in buildx_output.split('\n'):
            if 'Total:' in line:
                print(f"   {line}")

    print(f"\n💡 Cleanup command: docker system prune -a --volumes")
    print(f"   ⚠️  Warning: This will remove ALL unused Docker resources")

    return total_size


def check_homebrew():
    """Check Homebrew cache."""
    print("\n🍺 Homebrew")
    print("=" * 50)

    if not run_command(['which', 'brew']):
        print("   Homebrew not installed")
        return 0

    cache_path = run_command(['brew', '--cache'])
    if cache_path and os.path.exists(cache_path):
        size = get_dir_size(cache_path)
        print(f"   Cache location: {cache_path}")
        print(f"   Cache size: {format_size(size)}")
        print(f"\n💡 Cleanup command: brew cleanup -s")
        return size

    return 0


def check_npm():
    """Check npm cache."""
    print("\n📦 npm")
    print("=" * 50)

    if not run_command(['which', 'npm']):
        print("   npm not installed")
        return 0

    cache_path = run_command(['npm', 'config', 'get', 'cache'])
    if cache_path and cache_path != 'undefined' and os.path.exists(cache_path):
        size = get_dir_size(cache_path)
        print(f"   Cache location: {cache_path}")
        print(f"   Cache size: {format_size(size)}")
        print(f"\n💡 Cleanup command: npm cache clean --force")
        return size

    return 0


def check_pip():
    """Check pip cache."""
    print("\n🐍 pip")
    print("=" * 50)

    # Try pip3 first
    pip_cmd = 'pip3' if run_command(['which', 'pip3']) else 'pip'

    if not run_command(['which', pip_cmd]):
        print("   pip not installed")
        return 0

    cache_dir = run_command([pip_cmd, 'cache', 'dir'])
    if cache_dir and os.path.exists(cache_dir):
        size = get_dir_size(cache_dir)
        print(f"   Cache location: {cache_dir}")
        print(f"   Cache size: {format_size(size)}")
        print(f"\n💡 Cleanup command: {pip_cmd} cache purge")
        return size

    return 0


def check_old_git_repos():
    """Find large .git directories in archived projects."""
    print("\n📁 Old Git Repositories")
    print("=" * 50)

    home = Path.home()
    common_project_dirs = [
        home / 'Projects',
        home / 'workspace',
        home / 'dev',
        home / 'src',
        home / 'code'
    ]

    git_repos = []
    total_size = 0

    for project_dir in common_project_dirs:
        if not project_dir.exists():
            continue

        # Find .git directories
        try:
            result = subprocess.run(
                ['find', str(project_dir), '-name', '.git', '-type', 'd', '-maxdepth', 3],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                for git_path in result.stdout.strip().split('\n'):
                    if git_path:
                        size = get_dir_size(git_path)
                        if size > 10 * 1024 * 1024:  # > 10 MB
                            git_repos.append((git_path, size))
                            total_size += size
        except subprocess.TimeoutExpired:
            continue

    if git_repos:
        # Sort by size
        git_repos.sort(key=lambda x: x[1], reverse=True)

        print(f"   Found {len(git_repos)} .git directories > 10 MB")
        print(f"\n   Top 10 largest:")
        for path, size in git_repos[:10]:
            # Get parent directory name (project name)
            project_name = Path(path).parent.name
            print(f"   - {project_name:<30} {format_size(size)}")

        print(f"\n   Total: {format_size(total_size)}")
        print(f"\n💡 If these are archived projects, consider:")
        print(f"   1. Delete .git history: rm -rf <project>/.git")
        print(f"   2. Or compress entire project: tar -czf archive.tar.gz <project>")
    else:
        print("   No large .git directories found in common project locations")

    return total_size


def main():
    print("🔍 Development Environment Analysis")
    print("=" * 50)

    total_savings = 0

    # Check each component
    docker_size = check_docker()
    brew_size = check_homebrew()
    npm_size = check_npm()
    pip_size = check_pip()
    git_size = check_old_git_repos()

    # Summary
    print("\n\n📊 Summary")
    print("=" * 50)
    if docker_size:
        print(f"Docker:              {format_size(docker_size)}")
        total_savings += docker_size
    if brew_size:
        print(f"Homebrew cache:      {format_size(brew_size)}")
        total_savings += brew_size
    if npm_size:
        print(f"npm cache:           {format_size(npm_size)}")
        total_savings += npm_size
    if pip_size:
        print(f"pip cache:           {format_size(pip_size)}")
        total_savings += pip_size
    if git_size:
        print(f"Old .git repos:      {format_size(git_size)}")
        total_savings += git_size

    print("-" * 50)
    print(f"Potential savings:   {format_size(total_savings)}")

    print("\n💡 Next Steps:")
    print("   1. Review Docker volumes before cleanup (may contain data)")
    print("   2. Package manager caches are safe to delete")
    print("   3. For .git directories, ensure project is truly archived")

    return 0


if __name__ == '__main__':
    sys.exit(main())
