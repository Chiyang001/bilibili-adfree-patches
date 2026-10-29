import com.android.tools.smali.baksmali.Adaptors.ClassDefinition;
import com.android.tools.smali.baksmali.BaksmaliOptions;
import com.android.tools.smali.baksmali.formatter.BaksmaliWriter;
import com.android.tools.smali.dexlib2.dexbacked.*;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.iface.Method;
import com.android.tools.smali.dexlib2.iface.ExceptionHandler;
import com.android.tools.smali.dexlib2.base.BaseTryBlock;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.ZipFile;

/** Canonical disassembly comparison of EVERY class in a replaced DEX. */
public final class CompareDex {
    static Map<String, ClassDef> classes(byte[] bytes) {
        DexBackedDexFile dex = new DexBackedDexFile(bytes, 0);
        Map<String, ClassDef> result = new TreeMap<>();
        for (int i = 0; i < dex.classCount; i++) {
            ClassDef c = (ClassDef) dex.classSection.get(i);
            if (result.put(c.getType(), c) != null) throw new IllegalStateException("Duplicate class");
        }
        return result;
    }
    static String canonical(ClassDef c) throws Exception { return canonical(c, true); }
    static String canonical(ClassDef c, boolean sequential) throws Exception {
        BaksmaliOptions options = new BaksmaliOptions();
        options.localsDirective = true;
        options.sequentialLabels = sequential;
        options.debugInfo = true;
        StringWriter target = new StringWriter();
        BaksmaliWriter writer = new BaksmaliWriter(target);
        new ClassDefinition(options, c).writeTo(writer);
        writer.flush();
        // The assembler elides explicitly encoded VM-default static values.
        // Elision preserves behavior; compare both representations equally.
        return target.toString().replaceAll(
            "(?m)^(\\.field [^\\n]+) = (?:false|0x0(?:[tTsSlL])?|0\\.0[fFdD]?|null)[ \\t]*$", "$1");
    }
    record ProtectedRange(int start, int end, String handlers) {}
    static List<ProtectedRange> mergeRanges(List<ProtectedRange> input) {
        List<ProtectedRange> result = new ArrayList<>();
        for (ProtectedRange range : input) {
            if (range.end() <= range.start()) throw new IllegalStateException("Empty exception range");
            if (!result.isEmpty()) {
                ProtectedRange previous = result.get(result.size() - 1);
                if (previous.end() > range.start()) throw new IllegalStateException("Overlapping exception ranges");
                if (previous.end() == range.start() && previous.handlers().equals(range.handlers())) {
                    result.set(result.size() - 1, new ProtectedRange(previous.start(), range.end(), previous.handlers()));
                    continue;
                }
            }
            result.add(range);
        }
        return result;
    }
    static Map<String, List<ProtectedRange>> exceptionCoverage(ClassDef c) {
        Map<String, List<ProtectedRange>> coverage = new TreeMap<>();
        for (Iterable group : new Iterable[] {c.getDirectMethods(), c.getVirtualMethods()}) {
            for (Object value : group) {
                Method method = (Method) value;
                List<ProtectedRange> ranges = new ArrayList<>();
                if (method.getImplementation() != null) {
                    for (Object item : method.getImplementation().getTryBlocks()) {
                        BaseTryBlock block = (BaseTryBlock) item;
                        StringBuilder handlers = new StringBuilder();
                        for (Object h : block.getExceptionHandlers()) {
                            ExceptionHandler handler = (ExceptionHandler) h;
                            handlers.append(handler.getExceptionType()).append('@').append(handler.getHandlerCodeAddress()).append(';');
                        }
                        ranges.add(new ProtectedRange(block.getStartCodeAddress(),
                            block.getStartCodeAddress() + block.getCodeUnitCount(), handlers.toString()));
                    }
                }
                coverage.put(method.toString(), mergeRanges(ranges));
            }
        }
        return coverage;
    }
    static String withoutTryDirectives(ClassDef c) throws Exception {
        StringBuilder result = new StringBuilder();
        // Address labels keep all branch/handler targets comparable after an
        // assembler merges adjacent protected ranges with identical handlers.
        for (String line : canonical(c, false).split("\\R")) {
            String t = line.strip();
            if (t.isEmpty() || t.startsWith(".catch ") || t.startsWith(".catchall ")
                || t.matches(":try_(start|end)_[0-9a-f]+")) continue;
            result.append(t).append('\n');
        }
        return result.toString();
    }
    static boolean equivalentTryEncoding(ClassDef a, ClassDef b) throws Exception {
        return exceptionCoverage(a).equals(exceptionCoverage(b)) && withoutTryDirectives(a).equals(withoutTryDirectives(b));
    }
    static void selfTest() {
        var split = List.of(new ProtectedRange(0, 4, "A@8;null@12;"), new ProtectedRange(4, 7, "A@8;null@12;"));
        var merged = List.of(new ProtectedRange(0, 7, "A@8;null@12;"));
        if (!mergeRanges(split).equals(merged)) throw new AssertionError("Adjacent ranges must merge");
        for (var different : List.of(
            List.of(new ProtectedRange(0, 7, "A@9;null@12;")),
            List.of(new ProtectedRange(0, 7, "null@12;A@8;")),
            List.of(new ProtectedRange(0, 4, "A@8;null@12;"), new ProtectedRange(5, 7, "A@8;null@12;")),
            List.of(new ProtectedRange(0, 8, "A@8;null@12;")))) {
            if (mergeRanges(split).equals(mergeRanges(different))) throw new AssertionError("Changed handler/order/gap/end accepted");
        }
        System.out.println("PASS: exception normalization preserves handler order, targets and exact coverage");
    }
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--selftest")) { selfTest(); return; }
        if (args.length != 5) throw new IllegalArgumentException("original.apk dex-name rebuilt.dex allowed.txt review-directory");
        byte[] original;
        try (ZipFile zip = new ZipFile(args[0])) {
            original = zip.getInputStream(zip.getEntry(args[1])).readAllBytes();
        }
        Map<String, ClassDef> before = classes(original);
        Map<String, ClassDef> after = classes(Files.readAllBytes(Path.of(args[2])));
        Set<String> allowed = new HashSet<>(Files.readAllLines(Path.of(args[3]), StandardCharsets.UTF_8));
        if (!after.keySet().containsAll(before.keySet())) throw new IllegalStateException("Classes removed: " + args[1]);
        Set<String> added = new HashSet<>(after.keySet());
        added.removeAll(before.keySet());
        if (!allowed.containsAll(added)) throw new IllegalStateException("Unplanned added classes: " + added);
        Path output = Path.of(args[4]);
        Files.createDirectories(output);
        int changed = 0;
        for (String type : after.keySet()) {
            String a = before.containsKey(type) ? canonical(before.get(type)) : "";
            String b = canonical(after.get(type));
            if (a.equals(b)) continue;
            if (!allowed.contains(type)) {
                if (before.containsKey(type) && equivalentTryEncoding(before.get(type), after.get(type))) {
                    System.out.println("NORMALIZED_TRY_BLOCKS\t" + args[1] + "\t" + type);
                    continue;
                }
                Files.writeString(output.resolve("unplanned.before.smali"), a, StandardCharsets.UTF_8);
                Files.writeString(output.resolve("unplanned.after.smali"), b, StandardCharsets.UTF_8);
                throw new IllegalStateException("Unplanned class change: " + args[1] + " " + type);
            }
            String name = String.format("%03d", ++changed);
            Files.writeString(output.resolve(name + ".before.smali"), a, StandardCharsets.UTF_8);
            Files.writeString(output.resolve(name + ".after.smali"), b, StandardCharsets.UTF_8);
            System.out.println("CHANGED\t" + type + "\t" + name);
        }
        if (changed == 0) throw new IllegalStateException("Expected patched classes");
        System.out.println("VERIFIED\t" + args[1] + "\t" + before.size() + "\t" + changed);
    }
}
