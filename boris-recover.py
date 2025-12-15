#!/usr/bin/env python3
"""
Restore a BORIS project file from a CSV export.

Usage:
    boris-recover path/to/exported.csv
    
Outputs a .boris file in the same directory with the same base name.
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path


def restore_boris(csv_path: Path) -> Path:
    """Convert a BORIS CSV export back to a .boris project file."""
    
    # Determine output path
    output_path = csv_path.with_suffix('.boris')
    
    # Read CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    if not rows:
        print("Error: CSV file is empty.", file=sys.stderr)
        sys.exit(1)
    
    # Extract metadata from first row
    obs_id = rows[0]['Observation id']
    obs_date = rows[0]['Observation date']
    media_duration = float(rows[0]['Media duration (s)'])
    fps = float(rows[0]['FPS'])
    media_file = rows[0]['Media file name']
    
    # Get unique subjects
    subjects = list(set(row['Subject'] for row in rows))
    
    # Analyze behaviors
    behavior_info = defaultdict(lambda: {'types': set(), 'category': None, 'modifiers': set()})
    for row in rows:
        beh = row['Behavior']
        behavior_info[beh]['types'].add(row['Behavior type'])
        behavior_info[beh]['category'] = row['Behavioral category']
        mod = row['Modifier #1']
        if mod and mod.strip():
            for m in mod.split(','):
                behavior_info[beh]['modifiers'].add(m.strip())
    
    # Build subjects configuration
    subjects_conf = {}
    for i, subj in enumerate(sorted(subjects)):
        subjects_conf[str(i)] = {
            "key": "",
            "name": subj,
            "description": ""
        }
    
    # Build behaviors configuration
    behaviors_conf = {}
    all_behaviors = sorted(behavior_info.keys())
    all_categories = list(set(info['category'] for info in behavior_info.values()))
    
    for i, beh in enumerate(all_behaviors):
        info = behavior_info[beh]
        is_state = 'START' in info['types'] or 'STOP' in info['types']
        
        modifiers = ""
        if info['modifiers']:
            modifiers = {
                "0": {
                    "name": "",
                    "description": "",
                    "type": 0,
                    "ask at stop": False,
                    "values": sorted(list(info['modifiers']))
                }
            }
        
        behaviors_conf[str(i)] = {
            "type": "State event" if is_state else "Point event",
            "key": "",
            "code": beh,
            "description": "",
            "color": "#aaaaaa",
            "category": info['category'],
            "modifiers": modifiers,
            "excluded": "",
            "coding map": ""
        }
    
    # Build events list [time, subject, behavior, modifier, comment, frame_index]
    events_list = []
    for row in rows:
        time_val = float(row['Time'])
        subject = row['Subject']
        behavior = row['Behavior']
        modifier = row['Modifier #1'] if row['Modifier #1'] and row['Modifier #1'].strip() else ""
        comment = row['Comment'] if row['Comment'] and row['Comment'] != 'NA' else ""
        
        try:
            frame_idx = int(row['Image index'])
        except (ValueError, KeyError):
            frame_idx = int(time_val * fps)
        
        events_list.append([time_val, subject, behavior, modifier, comment, frame_idx])
    
    events_list.sort(key=lambda x: x[0])
    
    # Build complete BORIS project
    boris_project = {
        "time_format": "hh:mm:ss",
        "project_date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "project_name": obs_id,
        "project_description": "Restored from CSV export",
        "project_format_version": "7.0",
        "subjects_conf": subjects_conf,
        "behaviors_conf": behaviors_conf,
        "observations": {
            obs_id: {
                "file": {
                    "1": [media_file],
                    "2": [], "3": [], "4": [],
                    "5": [], "6": [], "7": [], "8": []
                },
                "type": "MEDIA",
                "date": obs_date,
                "description": "",
                "time offset": 0.0,
                "events": events_list,
                "observation time interval": [0, 0],
                "independent_variables": {},
                "visualize_spectrogram": False,
                "visualize_waveform": False,
                "media_creation_date_as_offset": False,
                "media_scan_sampling_duration": 0,
                "image_display_duration": 1,
                "close_behaviors_between_videos": False,
                "media_info": {
                    "length": {media_file: media_duration},
                    "fps": {media_file: fps},
                    "hasVideo": {media_file: True},
                    "hasAudio": {media_file: True},
                    "offset": {"1": 0.0},
                    "zoom level": {"1": 1.0}
                }
            }
        },
        "behavioral_categories": all_categories,
        "independent_variables": {},
        "coding_map": {},
        "behaviors_coding_map": [],
        "converters": {},
        "behavioral_categories_config": {
            str(i): {"name": cat, "color": ""} 
            for i, cat in enumerate(all_categories)
        }
    }
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(boris_project, f, indent=None)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Restore a BORIS project file from a CSV export.',
        prog='boris-recover'
    )
    parser.add_argument(
        'csv_file',
        type=Path,
        help='Path to the BORIS CSV export file'
    )
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Overwrite existing .boris file if it exists'
    )
    
    args = parser.parse_args()
    
    if not args.csv_file.exists():
        print(f"Error: {args.csv_file} not found.", file=sys.stderr)
        sys.exit(1)
    
    if not args.csv_file.suffix.lower() == '.csv':
        print(f"Warning: {args.csv_file} does not have a .csv extension.", file=sys.stderr)
    
    output_path = args.csv_file.with_suffix('.boris')
    
    if output_path.exists() and not args.force:
        print(f"Error: {output_path} already exists.", file=sys.stderr)
        print("Use -f/--force to overwrite, or remove/rename the existing file.", file=sys.stderr)
        sys.exit(1)
    elif output_path.exists() and args.force:
        print(f"Warning: Overwriting {output_path}", file=sys.stderr)
    
    try:
        result = restore_boris(args.csv_file)
        print(f"Restored: {result}")
    except KeyError as e:
        print(f"Error: Missing expected column in CSV: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()