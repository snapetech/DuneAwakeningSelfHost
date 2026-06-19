#!/usr/bin/env bash
# Run a repo-owned Ghidra script against a staged Dune server binary.
#
# This is operator/research tooling only. It does not copy binaries from live
# hosts and does not mutate game state.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"

GHIDRA_HEADLESS="${GHIDRA_HEADLESS:-/opt/ghidra/support/analyzeHeadless}"
WORK_DIR="${DUNE_GHIDRA_WORK_DIR:-/tmp/ghidra-work}"
PROJECT_LOCATION=""
PROJECT_NAME="${DUNE_GHIDRA_PROJECT_NAME:-DuneServer}"
SCRIPT_PATH="$repo_root/scripts/research"
BINARY="${DUNE_GHIDRA_BINARY:-$WORK_DIR/server-bin}"
PROGRAM_NAME=""
SCRIPT=""
LOG=""
MODE="auto"
ANALYSIS="auto"
DRY_RUN=false
EXTRA_ARGS=()

usage() {
    cat <<'EOF'
Usage:
  scripts/research/run-ghidra-headless.sh --script SCRIPT [options]

Required:
  --script NAME|PATH            Ghidra postScript to run, such as DumpGmCommandSurface.java.

Options:
  --binary PATH                 Binary to import/process. Default: /tmp/ghidra-work/server-bin.
  --work-dir DIR                Working directory. Default: /tmp/ghidra-work.
  --project-location DIR        Ghidra project location. Default: <work-dir>/project.
  --project-name NAME           Ghidra project name. Default: DuneServer.
  --program-name NAME           Existing Ghidra program name. Default: basename(binary).
  --script-path DIR             Ghidra script path. Default: scripts/research.
  --log PATH                    Ghidra log file. Default: <work-dir>/<script-basename>-ghidra.log.
  --mode auto|import|process    auto imports if the project is missing, otherwise processes.
  --analysis auto|on|off        auto analyzes imports and skips analysis for existing projects.
  --dry-run                     Print the command without running it.
  --help                        Show this help.
  --                            Pass remaining args through to analyzeHeadless.

Examples:
  scripts/research/run-ghidra-headless.sh --script DumpGmCommandSurface.java
  scripts/research/run-ghidra-headless.sh --script FindLogoffTimers.java --analysis on
  scripts/research/run-ghidra-headless.sh --script FindSmugglersRunMp.java --mode process
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --binary)
            BINARY="${2:?missing value for --binary}"
            shift 2
            ;;
        --work-dir)
            WORK_DIR="${2:?missing value for --work-dir}"
            shift 2
            ;;
        --project-location)
            PROJECT_LOCATION="${2:?missing value for --project-location}"
            shift 2
            ;;
        --project-name)
            PROJECT_NAME="${2:?missing value for --project-name}"
            shift 2
            ;;
        --program-name)
            PROGRAM_NAME="${2:?missing value for --program-name}"
            shift 2
            ;;
        --script)
            SCRIPT="${2:?missing value for --script}"
            shift 2
            ;;
        --script-path)
            SCRIPT_PATH="${2:?missing value for --script-path}"
            shift 2
            ;;
        --log)
            LOG="${2:?missing value for --log}"
            shift 2
            ;;
        --mode)
            MODE="${2:?missing value for --mode}"
            shift 2
            ;;
        --analysis)
            ANALYSIS="${2:?missing value for --analysis}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            EXTRA_ARGS+=("$@")
            break
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

[[ -n "$SCRIPT" ]] || die "--script is required"
[[ "$MODE" =~ ^(auto|import|process)$ ]] || die "--mode must be auto, import, or process"
[[ "$ANALYSIS" =~ ^(auto|on|off)$ ]] || die "--analysis must be auto, on, or off"
if [[ "$DRY_RUN" != true ]]; then
    [[ -x "$GHIDRA_HEADLESS" ]] || die "Ghidra headless runner not executable: $GHIDRA_HEADLESS"
fi

if [[ -z "$PROJECT_LOCATION" ]]; then
    PROJECT_LOCATION="$WORK_DIR/project"
fi

if [[ -z "$PROGRAM_NAME" ]]; then
    PROGRAM_NAME="$(basename "$BINARY")"
fi

if [[ "$SCRIPT" == */* ]]; then
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT")" && pwd)"
    SCRIPT_NAME="$(basename "$SCRIPT")"
else
    SCRIPT_DIR="$SCRIPT_PATH"
    SCRIPT_NAME="$SCRIPT"
fi

[[ -f "$SCRIPT_DIR/$SCRIPT_NAME" ]] || die "Ghidra script not found: $SCRIPT_DIR/$SCRIPT_NAME"

project_file="$PROJECT_LOCATION/$PROJECT_NAME.gpr"
resolved_mode="$MODE"
if [[ "$resolved_mode" == "auto" ]]; then
    if [[ -f "$project_file" || -d "$PROJECT_LOCATION/$PROJECT_NAME.rep" ]]; then
        resolved_mode="process"
    else
        resolved_mode="import"
    fi
fi

if [[ "$DRY_RUN" != true ]]; then
    if [[ "$resolved_mode" == "import" ]]; then
        [[ -f "$BINARY" ]] || die "binary not found: $BINARY"
    fi
    mkdir -p "$WORK_DIR" "$PROJECT_LOCATION"
fi

if [[ -z "$LOG" ]]; then
    LOG="$WORK_DIR/${SCRIPT_NAME%.*}-ghidra.log"
fi

cmd=("$GHIDRA_HEADLESS" "$PROJECT_LOCATION" "$PROJECT_NAME")

case "$resolved_mode" in
    import)
        cmd+=("-import" "$BINARY")
        ;;
    process)
        cmd+=("-process" "$PROGRAM_NAME")
        ;;
esac

if [[ "$ANALYSIS" == "off" || ( "$ANALYSIS" == "auto" && "$resolved_mode" == "process" ) ]]; then
    cmd+=("-noanalysis")
fi

cmd+=("-postScript" "$SCRIPT_NAME" "-scriptPath" "$SCRIPT_DIR" "-log" "$LOG")

if [[ "${#EXTRA_ARGS[@]}" -gt 0 ]]; then
    cmd+=("${EXTRA_ARGS[@]}")
fi

echo "Ghidra mode: $resolved_mode"
echo "Analysis: $ANALYSIS"
echo "Project: $PROJECT_LOCATION / $PROJECT_NAME"
echo "Program: $PROGRAM_NAME"
echo "Script: $SCRIPT_DIR/$SCRIPT_NAME"
echo "Log: $LOG"
printf 'Command:'
printf ' %q' "${cmd[@]}"
printf '\n'

if [[ "$DRY_RUN" == true ]]; then
    exit 0
fi

export DUNE_GHIDRA_WORK_DIR="$WORK_DIR"
exec "${cmd[@]}"
