#!/usr/bin/env python3
"""
Wallpaper Quality Manager
Manages wallpaper collection by upscaling images to meet minimum resolution requirements.
"""

import os
import sys
import subprocess
import signal
from pathlib import Path
from PIL import Image
from typing import List, Tuple, Dict
from dataclasses import dataclass
from collections import defaultdict

# Configuration
WALLPAPER_DIR = "."  # UPDATE THIS PATH
TARGET_WIDTH = 2560
TARGET_HEIGHT = 1440
MAX_UPSCALE_FACTOR = 4
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_THEME = "gruvbox"  # Change this to your preferred theme


@dataclass
class ImageInfo:
    path: Path
    width: int
    height: int
    scale_needed: float
    category: str  # 'good', 'upscalable', 'too_low'


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n⚠️  Operation cancelled by user.")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def get_scale_factor(width: int, height: int) -> float:
    """Calculate scale factor needed to meet target resolution"""
    width_scale = TARGET_WIDTH / width
    height_scale = TARGET_HEIGHT / height
    return max(width_scale, height_scale)


def scan_images(directory: Path) -> List[ImageInfo]:
    """Recursively scan directory for images and categorize them"""
    images = []

    print(f"🔍 Scanning {directory}...")

    for file_path in directory.rglob("*"):
        if file_path.suffix.lower() not in SUPPORTED_FORMATS:
            continue

        if "_upscaled" in file_path.stem:
            continue

        try:
            with Image.open(file_path) as img:
                width, height = img.size
                scale_needed = get_scale_factor(width, height)

                if scale_needed <= 1.0:
                    category = "good"
                elif scale_needed <= MAX_UPSCALE_FACTOR:
                    category = "upscalable"
                else:
                    category = "too_low"

                images.append(
                    ImageInfo(
                        path=file_path,
                        width=width,
                        height=height,
                        scale_needed=scale_needed,
                        category=category,
                    )
                )
        except Exception as e:
            print(f"⚠️  Error reading {file_path}: {e}")

    return images


def print_summary(images: List[ImageInfo]):
    """Print scan summary"""
    good = [img for img in images if img.category == "good"]
    upscalable = [img for img in images if img.category == "upscalable"]
    too_low = [img for img in images if img.category == "too_low"]

    print("\n" + "=" * 60)
    print("📊 SCAN SUMMARY")
    print("=" * 60)
    print(f"✅ Good quality (≥{TARGET_WIDTH}x{TARGET_HEIGHT}): {len(good)}")
    print(f"🔄 Can be upscaled (needs 2-4x): {len(upscalable)}")
    print(f"❌ Too low quality (needs >{MAX_UPSCALE_FACTOR}x): {len(too_low)}")
    print(f"📁 Total images found: {len(images)}")
    print("=" * 60 + "\n")


def group_by_scale(images: List[ImageInfo]) -> Dict[int, List[ImageInfo]]:
    """Group upscalable images by required scale factor"""
    groups = defaultdict(list)
    for img in images:
        if img.category == "upscalable":
            # Round up to nearest integer scale
            scale = int(img.scale_needed) + (1 if img.scale_needed % 1 > 0 else 0)
            scale = min(scale, MAX_UPSCALE_FACTOR)
            groups[scale].append(img)
    return dict(groups)


def convert_image_theme(
    image_path: Path, theme: str, verbose: bool = False
) -> Tuple[bool, Path, str]:
    """Convert image to specified theme using gowall"""
    output_path = image_path.parent / f"{image_path.stem}_{theme}{image_path.suffix}"
    error_msg = ""

    try:
        # Run gowall convert command
        # Syntax: gowall convert <input> -t <theme> --output <output>
        cmd = [
            "gowall",
            "convert",
            str(image_path),
            "-t",
            theme,
            "--output",
            str(output_path),
        ]

        if verbose:
            print(f"\n  Command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, text=True
        )

        if verbose:
            if result.stdout:
                print(f"  stdout: {result.stdout}")
            if result.stderr:
                print(f"  stderr: {result.stderr}")
            print(f"  return code: {result.returncode}")

        if result.returncode == 0 and output_path.exists():
            return True, output_path, ""
        else:
            error_msg = f"returncode={result.returncode}"
            if result.stderr:
                error_msg += f", stderr={result.stderr.strip()}"
            if not output_path.exists():
                error_msg += ", output file not created"
            return False, output_path, error_msg

    except subprocess.TimeoutExpired:
        error_msg = "Timeout (>5min)"
        if verbose:
            print(f"  ⏱️  Timeout processing {image_path.name}")
        return False, output_path, error_msg
    except Exception as e:
        error_msg = str(e)
        if verbose:
            print(f"  ⚠️  Error processing {image_path.name}: {e}")
        return False, output_path, error_msg


def batch_convert_theme(
    images: List[ImageInfo], theme: str, verbose: bool = False
) -> Tuple[List[Tuple[Path, Path]], List[Tuple[Path, str]]]:
    """Batch convert all images to specified theme"""
    successful = []
    failed = []
    total = len(images)

    print(f"\n🎨 Converting {total} images to '{theme}' theme...")
    if verbose:
        print("📝 Verbose logging enabled\n")

    for idx, img in enumerate(images, 1):
        print(
            f"  [{idx}/{total}] {img.path.name}...",
            end=" " if not verbose else "\n",
            flush=True,
        )

        success, output_path, error_msg = convert_image_theme(img.path, theme, verbose)

        if success:
            successful.append((img.path, output_path))
            if not verbose:
                print("✅")
        else:
            failed.append((img.path, error_msg))
            if verbose:
                print(f"  ❌ Error: {error_msg}\n")
            else:
                print("❌")

    return successful, failed


def get_available_themes() -> List[str]:
    """Get list of available gowall themes"""
    try:
        result = subprocess.run(
            ["gowall", "list"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            # Parse theme names from output
            themes = []
            for line in result.stdout.split("\n"):
                line = line.strip()
                if (
                    line
                    and not line.startswith("Available")
                    and not line.startswith("Custom")
                ):
                    # Extract theme name (usually first word or before description)
                    parts = line.split()
                    if parts:
                        themes.append(parts[0])
            return themes
        return []
    except Exception:
        return []


def upscale_image(
    image_path: Path, scale: int, verbose: bool = False
) -> Tuple[bool, Path, str]:
    """Upscale a single image using gowall"""
    output_path = image_path.parent / f"{image_path.stem}_upscaled{image_path.suffix}"
    error_msg = ""

    try:
        # Run gowall upscale command
        # Syntax: gowall upscale <input> -s <scale> --output <output>
        cmd = [
            "gowall",
            "upscale",
            str(image_path),
            "-s",
            str(scale),
            "--output",
            str(output_path),
        ]

        if verbose:
            print(f"\n  Command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,  # 5 minute timeout per image
            text=True,
        )

        if verbose:
            if result.stdout:
                print(f"  stdout: {result.stdout}")
            if result.stderr:
                print(f"  stderr: {result.stderr}")
            print(f"  return code: {result.returncode}")

        if result.returncode == 0 and output_path.exists():
            return True, output_path, ""
        else:
            error_msg = f"returncode={result.returncode}"
            if result.stderr:
                error_msg += f", stderr={result.stderr.strip()}"
            if not output_path.exists():
                error_msg += ", output file not created"
            return False, output_path, error_msg

    except subprocess.TimeoutExpired:
        error_msg = "Timeout (>5min)"
        if verbose:
            print(f"  ⏱️  Timeout processing {image_path.name}")
        return False, output_path, error_msg
    except Exception as e:
        error_msg = str(e)
        if verbose:
            print(f"  ⚠️  Error processing {image_path.name}: {e}")
        return False, output_path, error_msg


def batch_upscale(
    images: List[ImageInfo], verbose: bool = False
) -> Tuple[List[Path], List[Tuple[Path, str]]]:
    """Batch upscale all images that need it"""
    groups = group_by_scale(images)

    if not groups:
        print("No images need upscaling.")
        return [], []

    successful = []
    failed = []
    total = sum(len(imgs) for imgs in groups.values())
    current = 0

    print(f"\n🚀 Starting upscaling of {total} images...")
    if verbose:
        print("📝 Verbose logging enabled\n")

    for scale, imgs in sorted(groups.items()):
        print(f"\n📐 Processing {len(imgs)} images at {scale}x scale...")

        for img in imgs:
            current += 1
            print(
                f"  [{current}/{total}] {img.path.name}...",
                end=" " if not verbose else "\n",
                flush=True,
            )

            success, output_path, error_msg = upscale_image(img.path, scale, verbose)

            if success:
                successful.append((img.path, output_path))
                if not verbose:
                    print("✅")
            else:
                failed.append((img.path, error_msg))
                if verbose:
                    print(f"  ❌ Error: {error_msg}\n")
                else:
                    print("❌")

    return successful, failed


def setup_gowall_config():
    """Ensure gowall config disables image preview for batch processing"""
    config_dir = Path.home() / ".config" / "gowall"
    config_file = config_dir / "config.yml"

    try:
        config_dir.mkdir(parents=True, exist_ok=True)

        # Check if config exists and has the setting
        if config_file.exists():
            with open(config_file, "r") as f:
                content = f.read()
                if "EnableImagePreviewing: false" in content:
                    return  # Already configured

        # Add or create config with preview disabled
        with open(config_file, "a") as f:
            if config_file.stat().st_size > 0:
                f.write("\n")
            f.write("# Added by Wallpaper Quality Manager for batch processing\n")
            f.write("EnableImagePreviewing: false\n")

        print("✅ Configured gowall to disable image preview for batch processing\n")
    except Exception as e:
        print(f"⚠️  Warning: Could not configure gowall config: {e}\n")


def ask_yes_no(question: str, default: bool = True) -> bool:
    """Ask user a yes/no question"""
    prompt = f"{question} [{'Y/n' if default else 'y/N'}]: "
    while True:
        response = input(prompt).strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'")


def main():
    print("🎨 Wallpaper Quality Manager")
    print(f"Target resolution: {TARGET_WIDTH}x{TARGET_HEIGHT}\n")

    # Validate directory
    wallpaper_dir = Path(WALLPAPER_DIR)
    if not wallpaper_dir.exists():
        print(f"❌ Error: Directory not found: {WALLPAPER_DIR}")
        print("Please update WALLPAPER_DIR in the script.")
        sys.exit(1)

    # Check if gowall is available
    print("🔍 Checking for gowall...")
    try:
        result = subprocess.run(
            ["gowall", "--version"], capture_output=True, text=True, check=True
        )
        print(
            f"✅ Found gowall: {result.stdout.strip() if result.stdout else 'version check passed'}\n"
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print("❌ Error: 'gowall' command not found or failed.")
        print("Please install gowall first: https://github.com/Achno/gowall")
        if isinstance(e, subprocess.CalledProcessError):
            print(f"Error details: {e.stderr}")
        sys.exit(1)

    # Test gowall with a simple command
    print("🧪 Testing gowall availability...")
    try:
        result = subprocess.run(
            ["gowall", "--help"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            print(f"⚠️  Warning: gowall --help returned code {result.returncode}")
            print(f"stderr: {result.stderr}")
        else:
            print("✅ gowall is responding correctly\n")
    except Exception as e:
        print(f"⚠️  Warning: Could not test gowall: {e}\n")

    # Setup gowall config to disable image preview
    setup_gowall_config()

    # Scan directory
    images = scan_images(wallpaper_dir)

    if not images:
        print("No images found in directory.")
        sys.exit(0)

    print_summary(images)

    upscalable = [img for img in images if img.category == "upscalable"]
    too_low = [img for img in images if img.category == "too_low"]
    all_images = images

    if not upscalable and not too_low:
        print("✨ All images already meet quality requirements!")
        # Still allow theme conversion
        if ask_yes_no(
            "\n🎨 Would you like to convert images to a different theme?", False
        ):
            theme = (
                input(f"Enter theme name (default: {DEFAULT_THEME}): ").strip()
                or DEFAULT_THEME
            )

            available_themes = get_available_themes()
            if available_themes:
                print(f"\n📋 Available themes: {', '.join(available_themes[:10])}")
                if len(available_themes) > 10:
                    print(
                        f"   ... and {len(available_themes) - 10} more (use 'gowall list' to see all)"
                    )

            verbose = ask_yes_no("\n🐛 Enable verbose logging for debugging?", False)
            successful, failed = batch_convert_theme(all_images, theme, verbose)

            print("\n" + "=" * 60)
            print(f"✅ Successfully converted: {len(successful)}")
            print(f"❌ Failed: {len(failed)}")
            print("=" * 60)

            if failed and not verbose:
                print("\n📋 Sample of errors (first 5):")
                for img_path, error_msg in failed[:5]:
                    print(f"  • {img_path.name}: {error_msg}")
                if len(failed) > 5:
                    print(f"  ... and {len(failed) - 5} more errors")

            if successful and ask_yes_no(
                "\n🔄 Replace original files with converted versions?", False
            ):
                for original, converted in successful:
                    original.unlink()
                    converted.rename(original)
                print(f"✅ Replaced {len(successful)} original files.")
            elif successful:
                print(
                    f"✅ Kept both versions ({len(successful)} converted files saved)."
                )

        sys.exit(0)

    # Main menu
    print("What would you like to do?")
    print("1. Upscale images that need it")
    print("2. Convert all images to a theme")
    print("3. Upscale AND convert to theme")
    print("4. Delete all low-quality images")
    print("5. Cancel")

    choice = input("\nEnter choice (1-5): ").strip()

    if choice == "5":
        print("Operation cancelled.")
        sys.exit(0)

    if choice == "4":
        if ask_yes_no(
            f"⚠️  Delete {len(too_low)} images that are too low quality?", False
        ):
            for img in too_low:
                img.path.unlink()
            print(f"🗑️  Deleted {len(too_low)} images.")
        sys.exit(0)

    if choice not in ("1", "2", "3"):
        print("Invalid choice.")
        sys.exit(1)

    # Get theme if converting
    theme = None
    if choice in ("2", "3"):
        theme = (
            input(f"\n🎨 Enter theme name (default: {DEFAULT_THEME}): ").strip()
            or DEFAULT_THEME
        )

        available_themes = get_available_themes()
        if available_themes:
            print(f"\n📋 Available themes: {', '.join(available_themes[:10])}")
            if len(available_themes) > 10:
                print(
                    f"   ... and {len(available_themes) - 10} more (use 'gowall list' to see all)"
                )

    # Ask about verbose logging
    verbose = ask_yes_no("\n🐛 Enable verbose logging for debugging?", False)

    # Execute based on choice
    upscaled_images = []
    converted_images = []

    if choice == "1":
        # Upscale only
        successful, failed = batch_upscale(upscalable, verbose)
        upscaled_images = successful

        print("\n" + "=" * 60)
        print(f"✅ Successfully upscaled: {len(successful)}")
        print(f"❌ Failed: {len(failed)}")
        print("=" * 60)

        if failed and not verbose:
            print("\n📋 Sample of errors (first 5):")
            for img_path, error_msg in failed[:5]:
                print(f"  • {img_path.name}: {error_msg}")
            if len(failed) > 5:
                print(f"  ... and {len(failed) - 5} more errors")
            print("\nTip: Run again with verbose logging enabled to see full details.")

        if not successful:
            print("\nNo images were successfully upscaled.")
            sys.exit(0)

        # Ask about replacing originals
        if ask_yes_no("\n🔄 Replace original files with upscaled versions?", False):
            for original, upscaled in successful:
                original.unlink()
                upscaled.rename(original)
            print(f"✅ Replaced {len(successful)} original files.")
        else:
            print(f"✅ Kept both versions ({len(successful)} upscaled files saved).")

        # Ask about failed upscales
        if failed and ask_yes_no(
            f"\n🗑️  Delete {len(failed)} files that failed upscaling?", False
        ):
            for img_path, _ in failed:
                img_path.unlink()
            print(f"🗑️  Deleted {len(failed)} failed images.")

    elif choice == "2":
        # Convert theme only
        successful, failed = batch_convert_theme(all_images, theme, verbose)
        converted_images = successful

        print("\n" + "=" * 60)
        print(f"✅ Successfully converted: {len(successful)}")
        print(f"❌ Failed: {len(failed)}")
        print("=" * 60)

        if failed and not verbose:
            print("\n📋 Sample of errors (first 5):")
            for img_path, error_msg in failed[:5]:
                print(f"  • {img_path.name}: {error_msg}")
            if len(failed) > 5:
                print(f"  ... and {len(failed) - 5} more errors")

        if not successful:
            print("\nNo images were successfully converted.")
            sys.exit(0)

        if ask_yes_no("\n🔄 Replace original files with converted versions?", False):
            for original, converted in successful:
                original.unlink()
                converted.rename(original)
            print(f"✅ Replaced {len(successful)} original files.")
        else:
            print(f"✅ Kept both versions ({len(successful)} converted files saved).")

    elif choice == "3":
        # Upscale AND convert
        print("\n📋 Step 1: Upscaling images that need it...")
        upscale_successful, upscale_failed = batch_upscale(upscalable, verbose)

        print("\n" + "=" * 60)
        print(f"✅ Successfully upscaled: {len(upscale_successful)}")
        print(f"❌ Failed upscaling: {len(upscale_failed)}")
        print("=" * 60)

        # Prepare list for theme conversion: good quality + successfully upscaled
        images_to_convert = []
        good_images = [img for img in images if img.category == "good"]

        # Add good quality images
        images_to_convert.extend(good_images)

        # Add upscaled images (use the new upscaled versions)
        for original, upscaled in upscale_successful:
            # Create ImageInfo for the upscaled version
            try:
                with Image.open(upscaled) as img:
                    width, height = img.size
                    images_to_convert.append(
                        ImageInfo(
                            path=upscaled,
                            width=width,
                            height=height,
                            scale_needed=1.0,
                            category="good",
                        )
                    )
            except Exception:
                pass

        if images_to_convert:
            print(
                f"\n📋 Step 2: Converting {len(images_to_convert)} images to '{theme}' theme..."
            )
            convert_successful, convert_failed = batch_convert_theme(
                images_to_convert, theme, verbose
            )

            print("\n" + "=" * 60)
            print(f"✅ Successfully converted: {len(convert_successful)}")
            print(f"❌ Failed conversion: {len(convert_failed)}")
            print("=" * 60)

            if convert_successful:
                if ask_yes_no(
                    "\n🔄 Replace files with theme-converted versions?", False
                ):
                    for original, converted in convert_successful:
                        original.unlink()
                        converted.rename(original)
                    print(
                        f"✅ Replaced {len(convert_successful)} files with themed versions."
                    )
                else:
                    print(
                        f"✅ Kept both versions ({len(convert_successful)} themed files saved)."
                    )

                # Clean up upscaled versions if they were replaced
                if upscale_successful:
                    if ask_yes_no("\n🗑️  Remove intermediate upscaled versions?", True):
                        for original, upscaled in upscale_successful:
                            if upscaled.exists():
                                upscaled.unlink()
                        print(
                            f"🗑️  Cleaned up {len(upscale_successful)} intermediate files."
                        )
        else:
            print("\nNo images available for theme conversion.")

    # Ask about too-low quality
    if too_low and ask_yes_no(
        f"\n🗑️  Delete {len(too_low)} images too low quality to upscale?", False
    ):
        for img in too_low:
            img.path.unlink()
        print(f"🗑️  Deleted {len(too_low)} low-quality images.")

    print("\n✨ Done! Your wallpaper collection has been optimized.")


if __name__ == "__main__":
    main()
