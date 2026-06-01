// Ghidra headless script to locate the non-base logoff timer paths in
// DuneSandboxServer-Linux-Shipping.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -postScript FindLogoffTimers.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/logoff-ghidra.log
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.DataUtilities;
import ghidra.program.model.data.StringDataType;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class FindLogoffTimers extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/logoff-findings.txt";
    private static final String[] NEEDLES = new String[] {
        "SetLeavingGameTimer",
        "ADunePlayerCharacter::SetLeavingGameTimer",
        "OnLeavingGame",
        "LogLogOffSystem",
        "logoff_persistence_end_time",
        "m_DefaultReconnectGracePeriodSeconds",
        "m_InstancedMapReconnectGracePeriodSeconds",
        "m_OvermapReturnGracePeriodSeconds",
        "RecordLogoffPersistenceEndTime"
    };
    private static final long[] SCALARS = new long[] {
        0x41f00000L, // 30.0f
        0x43960000L, // 300.0f
        30L,
        300L
    };

    private PrintWriter out;
    private final Set<Address> functions = new LinkedHashSet<>();

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());
            for (String needle : NEEDLES) {
                scanString(needle);
            }
            addExtraFunctions();
            if ("true".equalsIgnoreCase(envOrProperty("DUNE_LOGOFF_SCAN_SCALARS", "dune.logoff.scanScalars", "false"))) {
                scanScalarInstructions();
            }
            decompileCollectedFunctions();
        } finally {
            out.close();
        }
    }

    private void addExtraFunctions() {
        String extra = envOrProperty("DUNE_LOGOFF_EXTRA_FUNCTIONS", "dune.logoff.extraFunctions", "");
        if (extra.trim().isEmpty()) return;
        for (String item : extra.split(",")) {
            String value = item.trim();
            if (value.isEmpty()) continue;
            try {
                Address addr = toAddr(Long.parseUnsignedLong(value.replaceFirst("^0x", ""), 16));
                Function f = currentProgram.getFunctionManager().getFunctionContaining(addr);
                if (f != null) {
                    functions.add(f.getEntryPoint());
                    log("extra function " + f.getName() + " @ " + f.getEntryPoint());
                } else {
                    log("extra address has no containing function: " + addr);
                }
            } catch (Exception e) {
                log("bad extra function address: " + value + " error=" + e);
            }
        }
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }

    private void scanString(String needle) throws Exception {
        log("");
        log("== string: " + needle);
        Memory mem = currentProgram.getMemory();
        byte[] bytes = needle.getBytes("UTF-8");
        int hits = 0;
        for (MemoryBlock block : mem.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address found = mem.findBytes(block.getStart(), block.getEnd(), bytes, null, true, monitor);
            while (found != null) {
                hits++;
                log("hit " + found + " block=" + block.getName());
                try {
                    DataUtilities.createData(currentProgram, found, StringDataType.dataType, bytes.length + 1, false, DataUtilities.ClearDataMode.CLEAR_ALL_UNDEFINED_CONFLICT_DATA);
                } catch (Exception ignored) {
                    // Existing string/data markup is enough for reference lookup.
                }
                collectRefs(found);
                if (found.add(1).compareTo(block.getEnd()) >= 0) break;
                found = mem.findBytes(found.add(1), block.getEnd(), bytes, null, true, monitor);
            }
        }
        log("hits=" + hits);
    }

    private void collectRefs(Address target) {
        ReferenceManager rm = currentProgram.getReferenceManager();
        ReferenceIterator refs = rm.getReferencesTo(target);
        int count = 0;
        while (refs.hasNext()) {
            Reference ref = refs.next();
            count++;
            Address from = ref.getFromAddress();
            log("  ref " + from + " type=" + ref.getReferenceType());
            Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
            if (f != null) {
                functions.add(f.getEntryPoint());
                log("    function " + f.getName() + " @ " + f.getEntryPoint());
            }
        }
        log("refs=" + count);
    }

    private void scanScalarInstructions() {
        log("");
        log("== scalar instruction scan");
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            for (int i = 0; i < ins.getNumOperands(); i++) {
                for (Object obj : ins.getOpObjects(i)) {
                    if (!(obj instanceof Scalar)) continue;
                    long value = ((Scalar) obj).getUnsignedValue();
                    for (long target : SCALARS) {
                        if (value != target) continue;
                        Function f = currentProgram.getFunctionManager().getFunctionContaining(ins.getAddress());
                        if (f == null) continue;
                        String name = f.getName();
                        if (name.contains("Leaving") || name.contains("Logoff") || name.contains("FUN_")) {
                            functions.add(f.getEntryPoint());
                            log("scalar " + value + " at " + ins.getAddress() + " in " + name + " @ " + f.getEntryPoint() + ": " + ins);
                        }
                    }
                }
            }
        }
    }

    private void decompileCollectedFunctions() throws Exception {
        log("");
        log("== decompile collected functions: " + functions.size());
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        for (Address entry : functions) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f == null) continue;
            log("");
            log("-- function " + f.getName() + " @ " + entry);
            DecompileResults res = dec.decompileFunction(f, 90, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
                continue;
            }
            String[] lines = res.getDecompiledFunction().getC().split("\n");
            if ("true".equalsIgnoreCase(envOrProperty("DUNE_LOGOFF_FULL_DECOMPILE", "dune.logoff.fullDecompile", "false"))) {
                for (String line : lines) {
                    log("  " + line);
                }
                continue;
            }
            for (int i = 0; i < lines.length; i++) {
                String line = lines[i];
                if (line.contains("Leaving") ||
                    line.contains("Logoff") ||
                    line.contains("Reconnect") ||
                    line.contains("Persistence") ||
                    line.contains("30") ||
                    line.contains("300") ||
                    line.contains("0x41f00000") ||
                    line.contains("0x43960000")) {
                    int start = Math.max(0, i - 4);
                    int end = Math.min(lines.length, i + 5);
                    log("context line " + i);
                    for (int j = start; j < end; j++) {
                        log("  " + lines[j]);
                    }
                }
            }
        }
        dec.dispose();
    }

    private String envOrProperty(String envName, String propName, String fallback) {
        String env = System.getenv(envName);
        if (env != null && !env.isEmpty()) return env;
        return System.getProperty(propName, fallback);
    }
}
