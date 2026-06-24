// Dump exact Ghidra function decompiles and nearby branch/write context.
//
// Usage:
//   DUNE_GHIDRA_OFFSETS='0xd17c560,0xd17b5e0' \
//     scripts/research/run-ghidra-headless.sh --script DumpFocusedFunctions.java \
//       --mode process --analysis off
//
// Output:
//   $DUNE_GHIDRA_FOCUSED_OUT, $DUNE_GHIDRA_WORK_DIR/focused-functions.txt,
//   or /tmp/ghidra-work/focused-functions.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.InstructionPrototype;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Paths;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpFocusedFunctions extends GhidraScript {
    private static final String DEFAULT_OUT = "/tmp/ghidra-work/focused-functions.txt";

    private PrintWriter out;
    private DecompInterface decomp;

    @Override
    public void run() throws Exception {
        String outputPath = outputPath();
        out = new PrintWriter(new FileWriter(outputPath));
        decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try {
            log("Output: " + outputPath);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());
            String raw = System.getenv("DUNE_GHIDRA_OFFSETS");
            if (raw == null || raw.trim().isEmpty()) {
                raw = "0xd17c560,0xd17adf0,0xd17b5e0,0xd058610,0xd053120,0xd050f30,0xd177090,0xd059ac0,0xd05f0b0,0xd148810,0xcfdcb40,0xcf6e850,0xedf0f20,0xfa7ec00,0x12e2d0f0";
            }
            boolean forceExact = "1".equals(System.getenv("DUNE_GHIDRA_FORCE_EXACT_FUNCTIONS"));
            Set<Address> entries = new LinkedHashSet<>();
            for (String item : raw.split(",")) {
                String trimmed = item.trim();
                if (trimmed.isEmpty()) continue;
                long off = Long.decode(trimmed);
                Address addr = toAddr(off);
                Function f = forceExact ? currentProgram.getFunctionManager().getFunctionAt(addr)
                        : currentProgram.getFunctionManager().getFunctionContaining(addr);
                if (f == null) {
                    try {
                        disassemble(addr);
                        f = createFunction(addr, null);
                    } catch (Exception exc) {
                        log("    create-function failed: " + exc.getMessage());
                    }
                }
                log("");
                log("== requested " + trimmed + " addr=" + addr + " containing="
                        + (f == null ? "<none>" : f.getName() + " @ " + f.getEntryPoint()));
                if (f != null) entries.add(f.getEntryPoint());
            }
            for (Address entry : entries) {
                dumpFunction(entry);
            }
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpFunction(Address entry) throws Exception {
        Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (f == null) return;
        log("");
        log("-- function " + f.getName() + " @ " + f.getEntryPoint()
                + " size=" + f.getBody().getNumAddresses());
        dumpReferencesToEntry(f);
        dumpBranchContext(f);
        DecompileResults res = decomp.decompileFunction(f, 120, new ConsoleTaskMonitor());
        if (!res.decompileCompleted()) {
            log("decompile failed: " + res.getErrorMessage());
            return;
        }
        String[] lines = res.getDecompiledFunction().getC().split("\n");
        for (int i = 0; i < lines.length; i++) {
            log(String.format("  %04d: %s", i + 1, lines[i]));
        }
    }

    private void dumpReferencesToEntry(Function f) {
        log("  refs-to-entry:");
        ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint());
        int count = 0;
        while (it.hasNext() && count < 80) {
            Reference ref = it.next();
            Function from = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("    " + ref.getFromAddress() + " " + ref.getReferenceType()
                    + (from == null ? "" : " from=" + from.getName() + " @" + from.getEntryPoint()));
            count++;
        }
        if (count == 0) log("    <none>");
    }

    private void dumpBranchContext(Function f) {
        log("  branch/write context:");
        Instruction instr = currentProgram.getListing().getInstructionAt(f.getEntryPoint());
        int count = 0;
        while (instr != null && f.getBody().contains(instr.getAddress()) && count < 2500) {
            String mnemonic = instr.getMnemonicString();
            String text = instr.toString();
            boolean interesting = mnemonic.startsWith("J")
                    || mnemonic.equals("CALL")
                    || mnemonic.equals("CMP")
                    || mnemonic.equals("TEST")
                    || mnemonic.contains("UCOM")
                    || text.contains("0x6b")
                    || text.contains("0x6a")
                    || text.contains("0x69")
                    || text.contains("0x68")
                    || text.contains("[RAX + 0x79c]")
                    || text.contains("[RAX + 0x18]")
                    || text.contains("[RBX + 0x18]")
                    || text.contains("[RBP + -0x98]")
                    || text.contains("[RSP + 0x88]");
            if (interesting) {
                log("    " + instr.getAddress() + ": " + text);
            }
            instr = instr.getNext();
            count++;
        }
    }

    private void log(String line) {
        println(line);
        out.println(line);
    }

    private String outputPath() {
        String explicit = System.getenv("DUNE_GHIDRA_FOCUSED_OUT");
        if (explicit != null && !explicit.trim().isEmpty()) {
            return explicit.trim();
        }
        String workDir = System.getenv("DUNE_GHIDRA_WORK_DIR");
        if (workDir != null && !workDir.trim().isEmpty()) {
            return Paths.get(workDir.trim(), "focused-functions.txt").toString();
        }
        return DEFAULT_OUT;
    }
}
