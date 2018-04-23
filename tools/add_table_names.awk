#!/bin/awk -f



BEGIN {
    CONTROLLER_CONSTANTS_FILE="CONTROLLER_CONSTANTS_FILE" in ENVIRON ? ENVIRON["CONTROLLER_CONSTANTS_FILE"] : "/opt/stack/dragonflow/dragonflow/controller/common/constants.py";
    DATAPATH_ALLOCATION_FILE="DATAPATH_ALLOCATION_FILE" in ENVIRON ? ENVIRON["DATAPATH_ALLOCATION_FILE"] : "/var/run/dragonflow_datapath_allocation.json";
    # id_to_name from python file
    cmd = "awk '/^[^#].*TABLE[\\w]*/ {split($0, a, \"\\s*=\\s*\"); name=a[1]; id=a[2]; print id \" \" name}' " CONTROLLER_CONSTANTS_FILE
    while (cmd | getline) {
        split($0, a);
        id_to_name[ a[1] ] = a[2];
    }
    close(cmd)

    # id_to_name from jq
    jq_code = "\
. as $all | \n\
def invert: . as $in |\n\
        $in | keys as $ks |\n\
        reduce $ks[] as $k ({}; .[$in[$k] | tostring] = $k);\n\
def invert_and_merge: reduce . as $obj ({}; . |= $obj | invert);\n\
def map_keys(f): . as $obj | $obj | keys as $ks | reduce $ks[] as $k ({}; .[$k | f] = $obj[$k]);\n\
def on_exists($v2): . + \"/\" + $v2; \n\
def join($new): . as $orig | $new | keys as $n_ks |\n\
        reduce $n_ks[] as $k ($orig;\n\
                            .[$k] = (if ($orig | has($k)) then ($orig[$k] | on_exists($new[$k])) else $new[$k] end));\n\
def filter_keys(f): . as $obj | $obj | keys as $ks | reduce $ks[] as $k ({}; .[$k] = if ($k | f) then $obj[$k] else empty end);\n\
def to_output: . as $in | $in | keys as $ks | reduce $ks[] as $k (\"\"; . + $k + \" \" + $in[$k] + \"\\n\") | rtrimstr(\"\\n\");\n\
$all | filter_keys(. != \"dragonflow-legacy\") as $all |\n\
$all | keys as $k |\n\
reduce $k[] as $var ({}; . += (\n\
        ($all[$var][\"states\"] | map_keys($var + \".\" + .) | invert)\n\
                | join(($all[$var][\"entrypoints\"] | map_keys($var + \".in.\" + .) | invert))\n\
                | join(($all[$var][\"exitpoints\"] | map_keys($var + \".out.\" + .) | invert))\n\
        )) |\n\
to_output\n\
"
    cmd = "jq -r -f /dev/stdin " DATAPATH_ALLOCATION_FILE " << \"EOF\"\n" jq_code "\nEOF"
    while (cmd | getline) {
        split($0, a);
        id_to_name[ a[1] ] = a[2];
    }
    close(cmd)
}

{
  head = ""
  tail=$0
  while (match(tail, /(resubmit\(,|table=)([0-9]+)/, arr)) {
    repl = substr(tail, RSTART, RLENGTH)
    head = head substr(tail,1, RSTART-1) repl "(" id_to_name[arr[2]] ")"
    tail = substr(tail, RSTART+RLENGTH)
  }
  print head tail
}
