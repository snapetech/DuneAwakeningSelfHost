// Ghidra headless script for the decoded FNotificationsSystemMessage layout.
//
// The native server-command path is now known to receive an already decoded
// Dreamworld::FNotificationsSystemMessage object. This script focuses on the
// functions and tables that read or construct that object, especially the
// decoded string fields used by FUN_09f3ff90 and FUN_09ee73c0.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpFNotificationsSystemMessageLayout.java
//
// Output:
//   /tmp/ghidra-work/fnotifications-system-message-layout.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpFNotificationsSystemMessageLayout extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/fnotifications-system-message-layout.txt";
    private static final int MAX_DECOMPILES = 64;
    private static final int MAX_OFFSET_HITS_PER_FUNCTION = 12;
    private static final int MAX_OFFSET_FUNCTIONS = 220;

    private static final long TEXT_MIN = 0x09e00000L;
    private static final long TEXT_MAX = 0x0a100000L;

    private static final long[] FOCUS_FUNCTIONS = new long[] {
        0x09f8cf00L, // receive callback handoff wrapper
        0x09f6ecb0L, // dispatch callee
        0x09f3ff90L, // decoded notification dispatch
        0x09ee73c0L, // server-command notification handler
        0x09ee7970L, // auth/content extractor wrapper
        0x09eb7e60L, // auth/content extractor implementation
        0x09ec9f00L, // failure/log helper reached when message version/type gate fails
        0x09ede9a0L, // outbound serializer/publisher, useful for same struct layout
        0x09ed8710L, // RMQ listen loop
        0x0a05c5b0L, // generated receive delegate, calls FUN_09f8cf00
        0x0a05d070L, // generated receive delegate, calls FUN_09f8cf00
        0x0a05bfb0L, // PlayFab player session notification init owner path
        0x09fa5a70L, // queue/work-item setup
        0x09fa63c0L  // setup wrapper
    };

    private static final long[] DATA_TABLES = new long[] {
        0x1492b4c8L, // TBaseFunctorDelegateInstance<...FNotificationsSystemMessage...>
        0x1492b598L,
        0x1492b688L,
        0x1490e380L, // server-command handler log pointer tables
        0x1490e3a0L,
        0x1490e3c0L,
        0x1490e3e0L,
        0x1490e400L,
        0x1490e420L,
        0x15484140L, // JsonObjectStringToUStruct parse failure string pointer
        0x15484160L  // JsonObjectStringToUStruct deserialize failure string pointer
    };

    private static final String[] OFFSET_PATTERNS = new String[] {
        "+ 0x48]", "+ 0x50]", "+ 0x58]", "+ 0x60]", "+ 0x78]", "+ 0x80]",
        "+ 0x88]", "+ 0x90]", "+ 0x94]"
    };

    private PrintWriter out;
    private Memory mem;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Set<Address> decompileQueue = new LinkedHashSet<>();
    private final Set<Address> offsetHitFunctions = new LinkedHashSet<>();

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        mem = currentProgram.getMemory();
        refs = currentProgram.getReferenceManager();
        decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());
            dumpFocusFunctions();
            dumpDataTables();
            scanNotificationBandForOffsets();
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpFocusFunctions() {
        log("");
        log("== focus functions");
        for (long value : FOCUS_FUNCTIONS) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn == null) {
                dumpInstructions(addr, 40);
                continue;
            }
            addFunction(fn, "focus");
            dumpRefsTo(fn.getEntryPoint(), "refs to function entry", true);
            dumpFunctionInstructions(fn, true, 2200);
        }
    }

    private void dumpDataTables() {
        log("");
        log("== data tables");
        for (long value : DATA_TABLES) {
            Address addr = toAddr(value);
            log("");
            log("-- data/table 0x" + Long.toHexString(value) + " " + addr);
            dumpNearbyPointers(addr, 6);
            dumpRefsTo(addr, "refs to data/table", true);
        }
    }

    private void scanNotificationBandForOffsets() {
        log("");
        log("== instruction references to decoded notification offsets");
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        while (it.hasNext() && offsetHitFunctions.size() < MAX_OFFSET_FUNCTIONS) {
            Function fn = it.next();
            long entry = fn.getEntryPoint().getOffset();
            if (entry < TEXT_MIN || entry > TEXT_MAX) {
                continue;
            }
            int hits = dumpOffsetInstructions(fn);
            if (hits != 0) {
                offsetHitFunctions.add(fn.getEntryPoint());
                addFunction(fn, "offset-hit");
            }
        }
        log("offset-hit function count=" + offsetHitFunctions.size());
    }

    private int dumpOffsetInstructions(Function fn) {
        Instruction instr = currentProgram.getListing().getInstructionAt(fn.getEntryPoint());
        int hits = 0;
        int walked = 0;
        while (instr != null && fn.getBody().contains(instr.getAddress()) && walked < 3000) {
            String text = instr.toString();
            if (mentionsTargetOffset(text)) {
                if (hits == 0) {
                    log("");
                    log("-- offset-hit function " + fn.getName() + " @ " + fn.getEntryPoint());
                }
                if (hits < MAX_OFFSET_HITS_PER_FUNCTION) {
                    log("  " + instr.getAddress() + " " + text);
                    dumpRefsFrom(instr.getAddress(), "    ref-to");
                }
                hits++;
            }
            instr = instr.getNext();
            walked++;
        }
        if (hits > MAX_OFFSET_HITS_PER_FUNCTION) {
            log("  truncated offset hits=" + hits);
        }
        return hits;
    }

    private boolean mentionsTargetOffset(String text) {
        for (String pattern : OFFSET_PATTERNS) {
            if (text.indexOf(pattern) >= 0) {
                return true;
            }
        }
        return false;
    }

    private void dumpFunctionInstructions(Function fn, boolean onlyCallsRefsAndOffsets, int maxInstructions) {
        log("  body=" + fn.getBody().getMinAddress() + ".." + fn.getBody().getMaxAddress());
        Instruction instr = currentProgram.getListing().getInstructionAt(fn.getEntryPoint());
        int count = 0;
        while (instr != null && fn.getBody().contains(instr.getAddress()) && count < maxInstructions) {
            Reference[] from = refs.getReferencesFrom(instr.getAddress());
            boolean interesting = !onlyCallsRefsAndOffsets || instr.getFlowType().isCall() ||
                from.length != 0 || mentionsTargetOffset(instr.toString());
            if (interesting) {
                log("  insn " + instr.getAddress() + " " + instr);
                dumpRefsFrom(instr.getAddress(), "    ref-to");
            }
            instr = instr.getNext();
            count++;
        }
        if (count >= maxInstructions) {
            log("  truncated instruction walk at " + maxInstructions + " instructions");
        }
    }

    private void dumpInstructions(Address start, int maxInstructions) {
        Instruction instr = currentProgram.getListing().getInstructionAt(start);
        if (instr == null) {
            instr = currentProgram.getListing().getInstructionAfter(start);
        }
        int count = 0;
        while (instr != null && count < maxInstructions) {
            log("  insn " + instr.getAddress() + " " + instr);
            instr = instr.getNext();
            count++;
        }
    }

    private void dumpRefsFrom(Address from, String label) {
        Reference[] fromRefs = refs.getReferencesFrom(from);
        for (Reference ref : fromRefs) {
            Address to = ref.getToAddress();
            Function targetFn = currentProgram.getFunctionManager().getFunctionContaining(to);
            log(label + " " + to + " type=" + ref.getReferenceType() +
                (targetFn == null ? "" : " function=" + targetFn.getName() + " @ " + targetFn.getEntryPoint()));
            if (targetFn != null && isInterestingCallee(targetFn.getEntryPoint())) {
                addFunction(targetFn, "interesting-callee");
            }
        }
    }

    private boolean isInterestingCallee(Address entry) {
        long off = entry.getOffset();
        return off == 0x09f8cf00L || off == 0x09f6ecb0L || off == 0x09f3ff90L ||
            off == 0x09ee73c0L || off == 0x09ee7970L || off == 0x09eb7e60L ||
            off == 0x09ec9f00L || off == 0x09ede9a0L || off == 0x09f13850L ||
            off == 0x0a05c5b0L || off == 0x0a05d070L;
    }

    private void dumpRefsTo(Address addr, String label, boolean collect) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("    " + label + " " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (collect && fn != null) {
                addFunction(fn, label);
            }
        }
        if (count == 0) {
            log("    " + label + "=0");
        }
    }

    private void dumpNearbyPointers(Address ptrAddr, int radius) {
        for (int i = -radius; i <= radius; i++) {
            try {
                Address slot = ptrAddr.add((long)i * 8L);
                long raw = mem.getLong(slot);
                Address pointed = toAddr(raw);
                Function fn = currentProgram.getFunctionManager().getFunctionContaining(pointed);
                log("      slot" + signed(i) + " " + slot + " -> 0x" + Long.toHexString(raw) + " " + pointed +
                    (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()) +
                    " ascii=" + readInlineString(pointed, false, 96) +
                    " utf16=" + readInlineString(pointed, true, 96));
            } catch (Exception e) {
                log("      slot" + signed(i) + " <unreadable> " + e.getMessage());
            }
        }
    }

    private void addFunction(Function fn, String reason) {
        if (decompileQueue.size() < MAX_DECOMPILES && decompileQueue.add(fn.getEntryPoint())) {
            log("    queued-decompile " + fn.getName() + " @ " + fn.getEntryPoint() + " reason=" + reason);
        }
    }

    private void decompileCollected() throws Exception {
        log("");
        log("== decompile collected functions count=" + decompileQueue.size());
        for (Address entry : decompileQueue) {
            Function fn = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (fn == null) {
                continue;
            }
            log("");
            log("-- function " + fn.getName() + " @ " + fn.getEntryPoint());
            DecompileResults res = decomp.decompileFunction(fn, 120, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
            } else {
                log(res.getDecompiledFunction().getC());
            }
        }
    }

    private String readInlineString(Address addr, boolean utf16, int maxChars) {
        try {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < maxChars; i++) {
                int c;
                if (utf16) {
                    c = mem.getShort(addr.add((long)i * 2L)) & 0xffff;
                } else {
                    c = mem.getByte(addr.add(i)) & 0xff;
                }
                if (c == 0) {
                    break;
                }
                if (c < 0x20 || c > 0x7e) {
                    sb.append("\\x").append(Integer.toHexString(c));
                } else {
                    sb.append((char)c);
                }
            }
            return "\"" + sb.toString() + "\"";
        } catch (Exception e) {
            return "<unreadable>";
        }
    }

    private static String signed(int value) {
        return value < 0 ? Integer.toString(value) : "+" + value;
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
