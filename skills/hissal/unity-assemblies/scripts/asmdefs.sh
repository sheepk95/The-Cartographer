#!/usr/bin/env bash
# List every assembly definition in a Unity project or UPM package.
#
# Usage: asmdefs.sh [project-or-package-root]   (default: .)
#
# One tab-separated line per .asmdef:
#   name <TAB> guid <TAB> path <TAB> references
# guid is the .asmdef.meta's guid, or "no-meta" when the .meta is missing.
# references is comma-separated, each resolved to an assembly name; one that
# matches no listed assembly is printed as "?" plus the raw reference.
#
# Scans Assets/, Packages/ and Library/PackageCache/ under the root (the whole
# root when it has neither Assets/ nor Packages/, as in a package repo), and
# skips folders Unity ignores (hidden, or ending in "~"). Registry and git
# packages exist only in Library/PackageCache/: without it, their assemblies
# are missing and references to them print as unresolved, which the script
# says on stderr. Local packages outside the root ("file:" paths in
# Packages/manifest.json) are not scanned either; the script names them on stderr.
#
# Needs bash and grep only. Grep the output either way:
#   asmdefs.sh | grep -F "$(printf 'My.Assembly\t')"   name to guid
#   asmdefs.sh | grep -F "<guid>"                          guid to name

set -u

root=${1:-.}
root=${root%/}
cd "$root" || { echo "asmdefs.sh: cannot enter $root" >&2; exit 1; }

dirs=()
[ -d Assets ] && dirs+=(Assets)
[ -d Packages ] && dirs+=(Packages)
if [ -d Library/PackageCache ]; then
  dirs+=(Library/PackageCache)
else
  echo "asmdefs.sh: no Library/PackageCache here, so registry and git package assemblies are not listed and references to them print as unresolved." >&2
fi
[ ${#dirs[@]} -eq 0 ] && dirs=(.)

if [ -f Packages/manifest.json ]; then
  while IFS= read -r dep; do
    case $dep in
      '"file:../'*|'"file:/'*|'"file:'?:*) echo "asmdefs.sh: local package $dep is outside this root and not scanned; references into it print as unresolved." >&2 ;;
    esac
  done < <(grep -o '"file:[^"]*"' Packages/manifest.json)
fi

tab=$'\t'
nl=$'\n'
names=()
guids=()
paths=()
refs=()

while IFS= read -r file; do
  file=${file#./}
  case "/$file" in
    */.*|*~/*) continue ;;
  esac

  content=
  IFS= read -r -d '' content < "$file"

  # versionDefines entries carry their own "name" keys: drop them first.
  if [[ $content =~ \"versionDefines\"[[:space:]]*:[[:space:]]*\[[^]{}]*(\{[^{}]*\}[^]{}]*)*\] ]]; then
    content=${content/"${BASH_REMATCH[0]}"/}
  fi

  name=
  [[ $content =~ \"name\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] && name=${BASH_REMATCH[1]}

  reflist=
  if [[ $content =~ \"references\"[[:space:]]*:[[:space:]]*\[([^]]*)\] ]]; then
    rest=${BASH_REMATCH[1]}
    while [[ $rest =~ \"([^\"]*)\" ]]; do
      reflist+="${reflist:+,}${BASH_REMATCH[1]}"
      rest=${rest#*"${BASH_REMATCH[0]}"}
    done
  fi

  guid=no-meta
  if [ -f "$file.meta" ]; then
    meta=
    IFS= read -r -d '' meta < "$file.meta"
    [[ $meta =~ guid:[[:space:]]*([0-9a-fA-F]{32}) ]] && guid=${BASH_REMATCH[1]}
  fi

  names+=("$name")
  guids+=("$guid")
  paths+=("$file")
  refs+=("$reflist")
done < <(grep -rl --include='*.asmdef' '' "${dirs[@]}" 2>/dev/null)

# Lookup tables as newline-framed strings (bash 3.2 has no associative arrays).
by_guid=$nl
by_name=$nl
for i in "${!names[@]}"; do
  by_guid+="${guids[$i]}$tab${names[$i]}$nl"
  by_name+="${names[$i]}$nl"
done

for i in "${!names[@]}"; do
  out=
  IFS=, read -r -a items <<< "${refs[$i]}"
  for ref in ${items[@]+"${items[@]}"}; do
    case $ref in
      GUID:*)
        ref_guid=${ref#GUID:}
        case $by_guid in
          *"$nl$ref_guid$tab"*)
            after=${by_guid#*"$nl$ref_guid$tab"}
            ref=${after%%"$nl"*} ;;
          *) ref="?$ref" ;;
        esac ;;
      *)
        case $by_name in
          *"$nl$ref$nl"*) ;;
          *) ref="?$ref" ;;
        esac ;;
    esac
    out+="${out:+,}$ref"
  done
  printf '%s\t%s\t%s\t%s\n' "${names[$i]}" "${guids[$i]}" "${paths[$i]}" "$out"
done
