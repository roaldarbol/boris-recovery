#!/usr/bin/env python3
"""
Restore a BORIS project file from a CSV export.

Usage:
    boris-recover path/to/exported.csv
    
Automatically detects whether the CSV is a standard or aggregated export.
Outputs a .boris file in the same directory with the same base name.
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path


def parse_standard_csv(rows, fps):
    """Parse standard (non-aggregated) BORIS CSV export."""
    
    # Analyze behaviors
    behavior_info = defaultdict(lambda: {'types': set(), 'category': None, 'modifiers': set()})
    for row in rows:
        beh = row['Behavior']
        behavior_info[beh]['types'].add(row['Behavior type'])
        behavior_info[beh]['category'] = row['Behavioral category']
        mod = row.get('Modifier #1', '')
        if mod and mod.strip():
            for m in mod.split(','):
                behavior_info[beh]['modifiers'].add(m.strip())
    
    # Build events list [time, subject, behavior, modifier, comment, frame_index]
    events_list = []
    for row in rows:
        time_val = float(row['Time'])
        subject = row['Subject']
        behavior = row['Behavior']
        modifier = row.get('Modifier #1', '')
        modifier = modifier if modifier and modifier.strip() else ""
        comment = row.get('Comment', '')
        comment = comment if comment and comment != 'NA' else ""
        
        try:
            frame_idx = int(row['Image index'])
        except (ValueError, KeyError):
            frame_idx = int(time_val * fps)
        
        events_list.append([time_val, subject, behavior, modifier, comment, frame_idx])
    
    return behavior_info, events_list


def parse_aggregated_csv(rows, fps):
    """Parse aggregated BORIS CSV export."""
    
    # Aggregated format has: Start, Stop, Duration columns instead of Time + Behavior type
    # State events have start and stop times
    # Point events have same start/stop time (duration = 0 or near 0)
    
    def parse_number(val):
        if val is None:
            return 0.0
        val = val.strip()
        if val.count('.') > 1:
            parts = val.rsplit('.', 1)
            val = parts[0].replace('.', '') + '.' + parts[1]
        return float(val.replace(',', '.'))
    
    behavior_info = defaultdict(lambda: {'types': set(), 'category': None, 'modifiers': set()})
    events_list = []
    
    for row in rows:
        beh = row['Behavior']
        category = row.get('Behavioral category', '')
        behavior_info[beh]['category'] = category
        
        # Get modifier - could be in different columns
        modifier = ''
        for key in row.keys():
            if key.startswith('Modifier'):
                mod_val = row[key]
                if mod_val and mod_val.strip():
                    modifier = mod_val.strip()
                    for m in modifier.split(','):
                        behavior_info[beh]['modifiers'].add(m.strip())
                    break
        
        subject = row['Subject']
        
        # Handle both Comment and Comment start columns
        comment = row.get('Comment', '') or row.get('Comment start', '')
        comment = comment if comment and comment != 'NA' else ""
        
        start_time = parse_number(row['Start (s)'])
        stop_time = parse_number(row['Stop (s)'])
        
        # Check Behavior type if available, otherwise infer from duration
        beh_type = row.get('Behavior type', '').upper()
        
        if beh_type == 'POINT' or (beh_type == '' and abs(stop_time - start_time) < 0.001):
            # Point event
            behavior_info[beh]['types'].add('POINT')
            frame_idx = int(start_time * fps)
            events_list.append([start_time, subject, beh, modifier, comment, frame_idx])
        else:
            # State event
            behavior_info[beh]['types'].add('STATE')
            
            # Create START event
            start_frame = int(start_time * fps)
            events_list.append([start_time, subject, beh, modifier, comment, start_frame])
            
            # Create STOP event
            stop_frame = int(stop_time * fps)
            events_list.append([stop_time, subject, beh, "", "", stop_frame])
    
    return behavior_info, events_list


def detect_delimiter(csv_path: Path) -> str:
    """Detect the delimiter used in the CSV file."""
    with open(csv_path, 'r', encoding='utf-8') as f:
        first_line = f.readline()
    
    # Count potential delimiters
    semicolons = first_line.count(';')
    commas = first_line.count(',')
    
    return ';' if semicolons > commas else ','


def get_column(row, *possible_names, default=None):
    """Get a value from a row, trying multiple possible column names."""
    for name in possible_names:
        if name in row and row[name]:
            return row[name]
    return default


def detect_csv_format(rows):
    """Auto-detect whether CSV is standard or aggregated export."""
    if not rows:
        return None
    
    columns = set(rows[0].keys())
    
    # Aggregated exports have Start (s) and Stop (s) columns
    if 'Start (s)' in columns and 'Stop (s)' in columns:
        return 'aggregated'
    
    # Standard exports have Time and Behavior type columns
    if 'Time' in columns and 'Behavior type' in columns:
        return 'standard'
    
    return None


def restore_boris(csv_path: Path) -> Path:
    """Convert a BORIS CSV export back to a .boris project file."""
    
    # Determine output path
    output_path = csv_path.with_suffix('.boris')
    
    # Detect delimiter and read CSV
    delimiter = detect_delimiter(csv_path)
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)
    
    if not rows:
        print("Error: CSV file is empty.", file=sys.stderr)
        sys.exit(1)
    
    # Auto-detect format
    csv_format = detect_csv_format(rows)
    if csv_format is None:
        print("Error: Could not detect CSV format.", file=sys.stderr)
        print("Expected either standard export (with 'Time', 'Behavior type' columns)", file=sys.stderr)
        print("or aggregated export (with 'Start (s)', 'Stop (s)' columns).", file=sys.stderr)
        sys.exit(1)
    
    print(f"Detected format: {csv_format}", file=sys.stderr)
    
    # Extract metadata from first row (handle column name variations)
    first_row = rows[0]
    obs_id = first_row['Observation id']
    obs_date = first_row['Observation date']
    
    # Handle European number format (e.g., "64.242.400" should be "64242.400")
    def parse_number(val):
        if val is None:
            return 0.0
        val = val.strip()
        # Count periods - if more than one, it's European format with thousand separators
        if val.count('.') > 1:
            # Remove thousand separators, keep last period as decimal
            parts = val.rsplit('.', 1)
            val = parts[0].replace('.', '') + '.' + parts[1]
        return float(val.replace(',', '.'))
    
    media_duration = parse_number(get_column(first_row, 'Media duration (s)'))
    fps = parse_number(get_column(first_row, 'FPS', 'FPS (frame/s)', default='30'))
    media_file = first_row['Media file name']
    
    # Get unique subjects
    subjects = list(set(row['Subject'] for row in rows))
    
    # Parse events based on format
    if csv_format == 'aggregated':
        behavior_info, events_list = parse_aggregated_csv(rows, fps)
    else:
        behavior_info, events_list = parse_standard_csv(rows, fps)
    
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
    all_categories = list(set(info['category'] for info in behavior_info.values() if info['category']))
    
    for i, beh in enumerate(all_behaviors):
        info = behavior_info[beh]
        is_state = 'START' in info['types'] or 'STOP' in info['types'] or 'STATE' in info['types']
        
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
            "category": info['category'] or "",
            "modifiers": modifiers,
            "excluded": "",
            "coding map": ""
        }
    
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