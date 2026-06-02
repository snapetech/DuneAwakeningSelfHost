// Dump functions that reference specific data/string addresses.
//
// Usage:
//   DUNE_GHIDRA_ADDRS='0x05c5901e,0x14eb7170,0x14eb71b8' \
//     scripts/research/run-ghidra-headless.sh --script DumpDataXrefFunctions.java \
//       --mode process --analysis off
//
// Output:
//   /tmp/ghidra-work/data-xref-functions.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpDataXrefFunctions extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/data-xref-functions.txt";

    private PrintWriter out;
    private DecompInterface decomp;
    private final Set<Address> functions = new LinkedHashSet<>();

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());

            String raw = System.getenv("DUNE_GHIDRA_ADDRS");
            if (raw == null || raw.trim().isEmpty()) {
                raw = "0x05c5901e,0x14eb7170,0x14eb71b8,0x05aaaafa,0x14eb71f8,0x05bb5930,0x14c8e988";
            }
            for (String item : raw.split(",")) {
                String trimmed = item.trim();
                if (trimmed.isEmpty()) continue;
                dumpAddressRefs(toAddr(Long.decode(trimmed)), trimmed);
            }
            dumpFunctions();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpAddressRefs(Address addr, String label) {
        log("");
        log("== refs to " + label + " " + addr);
        int count = 0;
        ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(addr);
        while (it.hasNext()) {
            Reference ref = it.next();
            Address from = ref.getFromAddress();
            Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
            log("  " + from + " " + ref.getReferenceType()
                    + (f == null ? "" : " func=" + f.getName() + " @" + f.getEntryPoint()));
            if (f != null) functions.add(f.getEntryPoint());
            count++;
        }
        if (count == 0) log("  <none>");
    }

    private void dumpFunctions() throws Exception {
        log("");
        log("== functions " + functions.size());
        for (Address entry : functions) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f == null) continue;
            log("");
            log("-- function " + f.getName() + " @ " + f.getEntryPoint()
                    + " size=" + f.getBody().getNumAddresses());
            dumpBranchContext(f);
            DecompileResults res = decomp.decompileFunction(f, 120, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
                continue;
            }
            String[] lines = res.getDecompiledFunction().getC().split("\n");
            for (int i = 0; i < lines.length; i++) {
                log(String.format("  %04d: %s", i + 1, lines[i]));
            }
        }
    }

    private void dumpBranchContext(Function f) {
        log("  branch/write context:");
        Instruction ins = currentProgram.getListing().getInstructionAt(f.getEntryPoint());
        int count = 0;
        while (ins != null && f.getBody().contains(ins.getAddress()) && count < 3000) {
            String mnemonic = ins.getMnemonicString();
            String text = ins.toString();
            if (mnemonic.startsWith("J") || mnemonic.equals("CALL") || mnemonic.equals("CMP")
                    || mnemonic.equals("TEST") || text.contains("14eb71")
                    || text.contains("05c590") || text.contains("05aaa")) {
                log("    " + ins.getAddress() + ": " + text);
            }
            ins = ins.getNext();
            count++;
        }
    }

    private void log(String line) {
        println(line);
        out.println(line);
        out.flush();
    }
}
