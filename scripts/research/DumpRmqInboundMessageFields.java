// Ghidra headless script for the inbound RMQ message field helpers.
//
// DumpRmqRunnableVtables.java identified FUN_09edc750 as the inbound
// amqp_consume_message path. This companion script focuses on the helpers that
// extract delivery metadata, AMQP basic properties, body metadata, and the
// decoded object forwarded to registered consumers.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpRmqInboundMessageFields.java
//
// Output:
//   /tmp/ghidra-work/rmq-inbound-message-fields.txt
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

public class DumpRmqInboundMessageFields extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/rmq-inbound-message-fields.txt";
    private static final int MAX_NEEDLE_HITS = 8;

    private static final long[] FUNCTIONS = new long[] {
        0x09edc750L, // inbound amqp_consume_message loop
        0x09edd340L, // delivery metadata extractor
        0x09ee0490L, // named AMQP basic property extractor
        0x09edd540L, // inbound message scalar helper
        0x09edd810L, // inbound string/body-field helper
        0x09edd980L, // inbound message scalar/body helper
        0x09edda40L, // dispatch/copy decoded message to registered consumer
        0x09edcf00L, // consume-message error/status logger
        0x09edcfb0L, // AMQP status/message logger helper
        0x09eddc60L, // AMQP/body cleanup or string helper reached by receive paths
        0x09ec9f00L, // decoded-message copy helper reached by FUN_09edda40
        0x09eca180L  // decoded-message cleanup helper
    };

    private static final String[] NEEDLES = new String[] {
        "app_id",
        "user_id",
        "correlation_id",
        "reply_to",
        "content_type",
        "content_encoding",
        "message_id",
        "delivery_mode",
        "amqp_consume_message",
        "amqp_destroy_envelope",
        "Reading message"
    };

    private PrintWriter out;
    private Memory mem;
    private ReferenceManager refs;
    private DecompInterface decomp;

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
            dumpKnownFieldSummary();
            dumpFunctions();
            dumpNeedleRefs();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpKnownFieldSummary() {
        log("");
        log("== inbound receive call shape from FUN_09edc750");
        log("FUN_09edd340(local_c0, envelope)");
        log("FUN_09ee0490(local_f0, envelope, tmp, L\"app_id\", 8)");
        log("FUN_09ee0490(&local_78, envelope, tmp, L\"user_id\", 0x10)");
        log("FUN_09ee0490(&local_88, envelope, tmp, L\"correlation_id\", 0x400)");
        log("FUN_09ee0490(local_68, envelope, tmp, L\"reply_to\", 0x200)");
        log("uVar2 = FUN_09edd540(envelope)");
        log("FUN_09edd810(local_68 + 2)");
        log("uVar3 = FUN_09edd980(envelope)");
        log("FUN_09edda40(consumer + 0x160, local_decoded_message)");
        log("FUN_09edda40(global/default consumer, local_decoded_message)");
    }

    private void dumpNeedleRefs() throws Exception {
        log("");
        log("== string/property needle hits");
        for (String needle : NEEDLES) {
            log("");
            log("-- needle \"" + needle + "\" ascii");
            findNeedle(needle, false);
            log("-- needle \"" + needle + "\" utf16");
            findNeedle(needle, true);
        }
    }

    private void findNeedle(String needle, boolean utf16) throws Exception {
        byte[] pattern = utf16 ? utf16le(needle) : needle.getBytes(StandardCharsets.US_ASCII);
        Address cursor = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        int hits = 0;
        while (cursor != null && cursor.compareTo(max) <= 0) {
            Address hit = mem.findBytes(cursor, max, pattern, null, true, monitor);
            if (hit == null) {
                break;
            }
            hits++;
            log("  hit " + hit + " inline=" + readInlineString(hit, utf16, 160));
            dumpRefsTo(hit);
            findPointersTo(hit, 4);
            if (hits >= MAX_NEEDLE_HITS) {
                log("  hit count>=" + hits + " (scan capped)");
                return;
            }
            cursor = hit.add(1);
        }
        log("  hit count=" + hits);
    }

    private void findPointersTo(Address target, int maxHits) throws Exception {
        byte[] pattern = pointerBytes(target.getOffset());
        Address cursor = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        int hits = 0;
        while (cursor != null && cursor.compareTo(max) <= 0) {
            Address hit = mem.findBytes(cursor, max, pattern, null, true, monitor);
            if (hit == null) {
                break;
            }
            hits++;
            if (hits <= maxHits) {
                log("    pointer-hit " + hit);
                dumpRefsTo(hit);
            }
            cursor = hit.add(1);
        }
        if (hits > 0) {
            log("    pointer-hit count=" + hits);
        }
    }

    private void dumpFunctions() {
        log("");
        log("== focused decompile");
        for (long value : FUNCTIONS) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn == null) {
                continue;
            }
            dumpRefsTo(fn.getEntryPoint());
            DecompileResults res = decomp.decompileFunction(fn, 120, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
            } else {
                log(res.getDecompiledFunction().getC());
            }
        }
    }

    private void dumpRefsTo(Address addr) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("    ref " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
        }
        if (count == 0) {
            log("    refs=0");
        }
    }

    private String readInlineString(Address addr, boolean utf16, int maxChars) {
        try {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < maxChars; i++) {
                int c = utf16 ? mem.getShort(addr.add((long)i * 2L)) & 0xffff : mem.getByte(addr.add(i)) & 0xff;
                if (c == 0) {
                    break;
                }
                if (c < 0x20 || c > 0x7e) {
                    sb.append("\\x").append(Integer.toHexString(c));
                } else {
                    sb.append((char)c);
                }
            }
            return "\"" + sb + "\"";
        } catch (Exception e) {
            return "<unreadable>";
        }
    }

    private static byte[] utf16le(String s) {
        byte[] out = new byte[s.length() * 2];
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            out[i * 2] = (byte)(c & 0xff);
            out[i * 2 + 1] = (byte)((c >>> 8) & 0xff);
        }
        return out;
    }

    private static byte[] pointerBytes(long value) {
        byte[] pattern = new byte[8];
        for (int i = 0; i < 8; i++) {
            pattern[i] = (byte)((value >>> (8 * i)) & 0xff);
        }
        return pattern;
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
