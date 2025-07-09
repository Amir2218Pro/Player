#!/usr/bin/env python3
"""
Test script to check video detection and thumbnail generation
"""

import os
import sys
import subprocess
from pathlib import Path

def check_ffmpeg():
    """Check if ffmpeg is available"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg is available")
            return True
        else:
            print("❌ FFmpeg not working properly")
            return False
    except FileNotFoundError:
        print("❌ FFmpeg not found. Please install ffmpeg:")
        print("   Ubuntu/Debian: sudo apt install ffmpeg")
        print("   macOS: brew install ffmpeg")
        print("   Windows: Download from https://ffmpeg.org/")
        return False

def check_directories():
    """Check if required directories exist"""
    dirs = ['static/videos', 'static/thumbnails', 'static/subtitles']
    for dir_path in dirs:
        if os.path.exists(dir_path):
            print(f"✅ Directory exists: {dir_path}")
        else:
            os.makedirs(dir_path, exist_ok=True)
            print(f"📁 Created directory: {dir_path}")

def list_video_files():
    """List all video files in the videos directory"""
    video_dir = Path('static/videos')
    if not video_dir.exists():
        print("❌ Videos directory doesn't exist")
        return []
    
    video_extensions = {
        'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'ogg', 'ogv',
        'm4v', 'mpg', 'mpeg', 'mp2', 'mpe', 'mpv', 'm2v', '3gp', '3g2'
    }
    
    video_files = []
    for file_path in video_dir.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower().lstrip('.') in video_extensions:
            video_files.append(file_path)
    
    print(f"\n📹 Found {len(video_files)} video files:")
    for video_file in video_files:
        rel_path = video_file.relative_to(video_dir)
        print(f"   - {rel_path}")
    
    return video_files

def test_thumbnail_generation(video_file):
    """Test thumbnail generation for a specific video file"""
    print(f"\n🖼️  Testing thumbnail generation for: {video_file.name}")
    
    try:
        # Get video duration
        duration_cmd = [
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', str(video_file)
        ]
        
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
        
        if duration_result.returncode == 0:
            duration = float(duration_result.stdout.strip())
            print(f"   Duration: {duration:.2f} seconds")
            
            # Choose seek time
            if duration > 55:
                seek_time = '00:00:55'
            elif duration > 10:
                seek_time = '00:00:10'
            else:
                seek_time = '00:00:01'
            
            print(f"   Using seek time: {seek_time}")
            
            # Generate thumbnail
            thumbnail_path = f"static/thumbnails/test_{video_file.stem}.jpg"
            
            cmd = [
                'ffmpeg', '-i', str(video_file),
                '-ss', seek_time,
                '-vframes', '1',
                '-q:v', '2',
                '-vf', 'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2',
                '-y',
                thumbnail_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(thumbnail_path):
                print(f"   ✅ Thumbnail generated: {thumbnail_path}")
                return True
            else:
                print(f"   ❌ Thumbnail generation failed")
                print(f"   Error: {result.stderr}")
                return False
        else:
            print(f"   ❌ Could not get video duration")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    print("🎬 XPlayer Video Setup Test")
    print("=" * 40)
    
    # Check FFmpeg
    if not check_ffmpeg():
        sys.exit(1)
    
    # Check directories
    check_directories()
    
    # List video files
    video_files = list_video_files()
    
    if not video_files:
        print("\n⚠️  No video files found in static/videos/")
        print("   Please add some video files to test thumbnail generation")
        return
    
    # Test thumbnail generation for first few videos
    print("\n🧪 Testing thumbnail generation...")
    success_count = 0
    test_count = min(3, len(video_files))  # Test up to 3 videos
    
    for i, video_file in enumerate(video_files[:test_count]):
        if test_thumbnail_generation(video_file):
            success_count += 1
    
    print(f"\n📊 Results: {success_count}/{test_count} thumbnails generated successfully")
    
    if success_count == test_count:
        print("✅ All tests passed! Video detection and thumbnail generation should work.")
    else:
        print("⚠️  Some tests failed. Check the error messages above.")

if __name__ == "__main__":
    main()