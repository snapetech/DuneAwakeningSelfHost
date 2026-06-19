// Dump Ghidra xrefs for UE core anchor strings seen by the live loader canary.
//
// This is a static promotion pass for the gap between "target image contains
// UE strings" and "we have usable runtime anchors for names, objects,
// reflection, package loading, and ProcessEvent dispatch".
//
// Inputs:
//   DUNE_GHIDRA_UE_CANARY_LOG=/path/to/dune-server-probe-loader.log
//   DUNE_GHIDRA_UE_CORE_OUT=/tmp/ghidra-work/ue-core-anchor-xrefs.md
//
// Output:
//   ${DUNE_GHIDRA_UE_CORE_OUT:-${DUNE_GHIDRA_WORK_DIR:-/tmp/ghidra-work}/ue-core-anchor-xrefs.md}
//   plus a TSV next to it with the same basename and .tsv.
//
// @category Reverse Engineering

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DumpUeCoreAnchorXrefs extends GhidraScript {
    private static final int FALLBACK_HIT_LIMIT = 64;
    private static final Pattern LOG_HIT = Pattern.compile(
        "event=scan-hit .*?name=([^ ]+) .*?imageOffset=(0x[0-9a-fA-F]+)");

    private static final String[][] ANCHORS = new String[][] {
        {"names", "GName", "FName", "NamePool", "FNamePool", "GNames"},
        {"objects", "GUObjectArray", "GObjects", "UObject", "FUObjectArray"},
        {"world", "GWorld", "UWorld", "GetWorld", "WorldContext"},
        {"dispatch", "ProcessEvent", "UFunction", "CallFunctionByNameWithArguments"},
        {"package", "LoadObject", "LoadPackage", "StaticFindObject", "FindObject"},
        {"reflection", "UClass", "UStruct", "FProperty", "UProperty", "UEnum"}
    };

    private PrintWriter out;
    private PrintWriter tsv;
    private ReferenceManager refs;
    private long imageBase;
    private final Map<String, Set<Address>> explicitHits = new LinkedHashMap<>();
    private final Map<String, Set<Address>> candidateFunctions = new LinkedHashMap<>();

    @Override
    public void run() throws Exception {
        refs = currentProgram.getReferenceManager();
        imageBase = currentProgram.getImageBase().getOffset();

        String outPath = outputPath();
        File parent = new File(outPath).getParentFile();
        if (parent != null) parent.mkdirs();
        String tsvPath = outPath.replaceAll("\\.[^.]*$", "") + ".tsv";

        out = new PrintWriter(new FileWriter(outPath));
        tsv = new PrintWriter(new FileWriter(tsvPath));
        try {
            readCanaryLog();
            log("# UE Core Anchor Xrefs");
            log("");
            log("- Program: `" + currentProgram.getName() + "`");
            log("- Image base: `0x" + Long.toHexString(imageBase) + "`");
            log("- Canary log: `" + env("DUNE_GHIDRA_UE_CANARY_LOG", "") + "`");
            log("- TSV: `" + tsvPath + "`");
            log("");
            tsv.println("group\tname\thit\thitImageOffset\txrefFrom\txrefType\tfunction\tfunctionImageOffset\tfunctionSize");

            for (String[] group : ANCHORS) {
                dumpGroup(group);
            }
            dumpSummary();
        } finally {
            if (out != null) out.close();
            if (tsv != null) tsv.close();
        }
    }

    private String outputPath() {
        String explicit = env("DUNE_GHIDRA_UE_CORE_OUT", "");
        if (!explicit.isEmpty()) return explicit;
        String workDir = env("DUNE_GHIDRA_WORK_DIR", "/tmp/ghidra-work");
        return workDir + "/ue-core-anchor-xrefs.md";
    }

    private void readCanaryLog() throws Exception {
        String path = env("DUNE_GHIDRA_UE_CANARY_LOG", "");
        if (path.isEmpty()) return;
        File f = new File(path);
        if (!f.isFile()) return;
        try (BufferedReader br = new BufferedReader(new FileReader(f))) {
            String line;
            while ((line = br.readLine()) != null) {
                Matcher m = LOG_HIT.matcher(line);
                if (!m.find()) continue;
                String name = m.group(1);
                long rel = Long.decode(m.group(2));
                explicitHits.computeIfAbsent(name, k -> new LinkedHashSet<>()).add(toAddr(imageBase + rel));
            }
        }
    }

    private void dumpGroup(String[] groupSpec) throws Exception {
        String group = groupSpec[0];
        candidateFunctions.put(group, new LinkedHashSet<>());
        log("## " + group);
        log("");
        for (int i = 1; i < groupSpec.length; i++) {
            dumpNeedle(group, groupSpec[i]);
        }
        log("");
    }

    private void dumpNeedle(String group, String needle) throws Exception {
        Set<Address> hits = new LinkedHashSet<>();
        boolean hasExplicitHits = explicitHits.containsKey(needle);
        if (hasExplicitHits) {
            hits.addAll(explicitHits.get(needle));
        } else {
            hits.addAll(findStringBytes(needle, FALLBACK_HIT_LIMIT));
        }

        if (hits.isEmpty()) {
            log("- `" + needle + "`: no string hit");
            return;
        }

        int xrefCount = 0;
        Set<Address> needleFunctions = new LinkedHashSet<>();
        for (Address hit : hits) {
            Set<XrefRow> rows = xrefRows(hit, needle);
            if (rows.isEmpty()) {
                log(String.format("- `%s` hit `0x%x`: no Ghidra xref", needle, rel(hit)));
                continue;
            }
            for (XrefRow row : rows) {
                xrefCount++;
                if (row.functionEntry != null) {
                    needleFunctions.add(row.functionEntry);
                    candidateFunctions.get(group).add(row.functionEntry);
                }
                writeTsv(group, needle, hit, row);
            }
        }

        if (xrefCount == 0) {
            log(String.format("- `%s`: %d hits%s, no xrefs",
                needle, hits.size(), hasExplicitHits ? " from canary" : ""));
            return;
        }

        StringBuilder sb = new StringBuilder();
        for (Address entry : needleFunctions) {
            if (sb.length() > 0) sb.append(", ");
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            String fname = f == null ? "<unknown>" : f.getName();
            sb.append(String.format("`0x%x` `%s`", rel(entry), fname));
        }
        log(String.format("- `%s`: %d hits%s, %d xrefs, functions: %s",
            needle, hits.size(), hasExplicitHits ? " from canary" : "",
            xrefCount, sb.length() == 0 ? "<none>" : sb.toString()));
    }

    private Set<XrefRow> xrefRows(Address stringAddr, String needle) {
        Set<XrefRow> rows = new LinkedHashSet<>();
        int span = needle.length() + 1;
        for (int i = 0; i <= span; i++) {
            Address probe = stringAddr.add(i);
            ReferenceIterator rit = refs.getReferencesTo(probe);
            while (rit.hasNext()) {
                Reference ref = rit.next();
                Address from = ref.getFromAddress();
                Function fn = currentProgram.getFunctionManager().getFunctionContaining(from);
                Address entry = fn == null ? null : fn.getEntryPoint();
                rows.add(new XrefRow(from, ref.getReferenceType().toString(), entry));
            }
        }
        return rows;
    }

    private List<Address> findStringBytes(String needle, int limit) {
        List<Address> hits = new ArrayList<>();
        Memory mem = currentProgram.getMemory();
        for (byte[] pattern : Arrays.asList(asciiBytes(needle), utf16Bytes(needle))) {
            Address start = mem.getMinAddress();
            Address max = mem.getMaxAddress();
            while (start != null && start.compareTo(max) <= 0) {
                Address hit = mem.findBytes(start, max, pattern, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                if (hits.size() >= limit) return hits;
                start = hit.add(1);
            }
        }
        return hits;
    }

    private byte[] asciiBytes(String value) {
        return value.getBytes(StandardCharsets.US_ASCII);
    }

    private byte[] utf16Bytes(String value) {
        try {
            return value.getBytes("UTF-16LE");
        } catch (Exception exc) {
            throw new RuntimeException(exc);
        }
    }

    private void dumpSummary() {
        log("## Candidate Group Summary");
        log("");
        for (Map.Entry<String, Set<Address>> entry : candidateFunctions.entrySet()) {
            log("- `" + entry.getKey() + "`: " + entry.getValue().size() + " candidate functions");
        }
    }

    private void writeTsv(String group, String needle, Address hit, XrefRow row) {
        Function fn = row.functionEntry == null ? null : currentProgram.getFunctionManager().getFunctionAt(row.functionEntry);
        String fname = fn == null ? "" : fn.getName();
        String foff = row.functionEntry == null ? "" : "0x" + Long.toHexString(rel(row.functionEntry));
        String fsize = fn == null ? "" : Long.toString(fn.getBody().getNumAddresses());
        tsv.printf("%s\t%s\t%s\t0x%x\t%s\t%s\t%s\t%s\t%s%n",
            group, needle, hit, rel(hit), row.from, row.type, fname, foff, fsize);
    }

    private long rel(Address addr) {
        return addr.getOffset() - imageBase;
    }

    private String env(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isEmpty() ? fallback : value;
    }

    private void log(String line) {
        println(line);
        out.println(line);
    }

    private static class XrefRow {
        final Address from;
        final String type;
        final Address functionEntry;

        XrefRow(Address from, String type, Address functionEntry) {
            this.from = from;
            this.type = type;
            this.functionEntry = functionEntry;
        }

        @Override
        public int hashCode() {
            int h = from.hashCode();
            h = 31 * h + type.hashCode();
            h = 31 * h + (functionEntry == null ? 0 : functionEntry.hashCode());
            return h;
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof XrefRow)) return false;
            XrefRow other = (XrefRow)obj;
            if (!from.equals(other.from)) return false;
            if (!type.equals(other.type)) return false;
            if (functionEntry == null) return other.functionEntry == null;
            return functionEntry.equals(other.functionEntry);
        }
    }
}
