// Dump Landsraad runtime notification/state surfaces from the server binary.
//
// Usage:
//   scripts/research/run-ghidra-headless.sh \
//     --binary /tmp/ghidra-work/server-bin-survival-current \
//     --work-dir /tmp/ghidra-work-survival-current \
//     --project-location /tmp/ghidra-work-survival-current/project \
//     --project-name DuneServerSurvivalCurrent \
//     --script DumpLandsraadRuntimeSurface.java
//
// Output:
//   /tmp/ghidra-work/landsraad-runtime-surface.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpLandsraadRuntimeSurface extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/landsraad-runtime-surface.txt";
    private static final int MAX_FUNCTIONS = 80;

    private static final String[] NEEDLES = new String[] {
        "landsraad_notify_channel",
        "progress_updated",
        "guild_vote_changed",
        "house_rewards_changed",
        "progress_pressure",
        "OnLandsraadTermChanged",
        "ClientLandsraadTermChanged",
        "ELandsraadPeriod::Suspended",
        "ELandsraadPeriod::Competition",
        "ELandsraadPeriod::Voting",
        "ELandsraadPeriod::StartingTerm",
        "ELandsraadPeriod::EndingTerm",
        "ELandsraadStatus::Enabled",
        "ELandsraadStatus::Unavailable",
        "ELandsraadStatus::Disabled",
        "m_CurrentPeriod",
        "m_LandsraadStatus",
        "m_CurrentTermEnd",
        "m_VotingPeriodStartBeforeCoriolisCycleInSec",
        "m_VotingPeriodDurationInSec",
        "void ULandsraadManager::ListenNotificationEvents()",
        "void ULandsraadManager::SkipToNextPeriod()",
        "void ULandsraadManager::SkipToNewTestTerm(const FName &, int32)",
        "ULandsraadStateComponent",
        "ULandsraadReplicatedStateComponent",
        "ULandsraadManager"
    };

    private PrintWriter out;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Set<Address> functions = new LinkedHashSet<>();

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        refs = currentProgram.getReferenceManager();
        decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());
            dumpNeedles();
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpNeedles() throws Exception {
        log("");
        log("== landsraad runtime strings");
        for (String needle : NEEDLES) {
            log("");
            log("-- " + needle);
            dumpNeedle(needle, false);
            dumpNeedle(needle, true);
        }
    }

    private void dumpNeedle(String needle, boolean utf16) throws Exception {
        byte[] pattern = utf16 ? utf16le(needle) : needle.getBytes(StandardCharsets.UTF_8);
        Memory mem = currentProgram.getMemory();
        Address cursor = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        int hits = 0;
        while (cursor != null && cursor.compareTo(max) <= 0) {
            Address hit = mem.findBytes(cursor, max, pattern, null, true, monitor);
            if (hit == null) {
                break;
            }
            hits++;
            log("hit " + hit + " encoding=" + (utf16 ? "utf16le" : "ascii"));
            dumpRefs(hit);
            cursor = hit.add(1);
        }
        log("hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
    }

    private void dumpRefs(Address hit) {
        ReferenceIterator it = refs.getReferencesTo(hit);
        int refsCount = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            refsCount++;
            Address from = ref.getFromAddress();
            Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
            log("  ref " + from + " type=" + ref.getReferenceType() +
                    (f == null ? "" : " function=" + f.getName() + " @ " + f.getEntryPoint()));
            if (f != null && functions.size() < MAX_FUNCTIONS) {
                functions.add(f.getEntryPoint());
            }
            dumpIndirectRefs(from);
        }
        log("  refs=" + refsCount);
    }

    private void dumpIndirectRefs(Address pointerAddress) {
        ReferenceIterator it = refs.getReferencesTo(pointerAddress);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("    indirect ref " + ref.getFromAddress() + " -> " + pointerAddress +
                    " type=" + ref.getReferenceType() +
                    (f == null ? "" : " function=" + f.getName() + " @ " + f.getEntryPoint()));
            if (f != null && functions.size() < MAX_FUNCTIONS) {
                functions.add(f.getEntryPoint());
            }
        }
        if (count != 0) {
            log("    indirect refs=" + count);
        }
    }

    private void decompileCollected() throws Exception {
        log("");
        log("== decompile collected functions count=" + functions.size());
        for (Address entry : functions) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f == null) {
                continue;
            }
            log("");
            log("-- function " + f.getName() + " @ " + entry + " size=" + f.getBody().getNumAddresses());
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

    private static byte[] utf16le(String value) {
        byte[] out = new byte[value.length() * 2];
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            out[i * 2] = (byte)(c & 0xff);
            out[i * 2 + 1] = (byte)((c >> 8) & 0xff);
        }
        return out;
    }

    private void log(String line) {
        println(line);
        out.println(line);
        out.flush();
    }
}
