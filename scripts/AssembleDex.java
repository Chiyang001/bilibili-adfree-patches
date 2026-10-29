import brut.androlib.smali.SmaliBuilder;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.writer.builder.DexBuilder;
import com.android.tools.smali.dexlib2.writer.io.FileDataStore;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Assemble one original DEX's complete class set, without rebuilding resources. */
public final class AssembleDex {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("smali-directory output.dex");
        List<Path> files;
        try (var paths = Files.walk(Path.of(args[0]))) {
            files = paths.filter(p -> p.toString().endsWith(".smali")).sorted().toList();
        }
        if (files.isEmpty()) throw new IllegalStateException("No smali files");
        // The supplied APK uses DEX 037 and minSdk 24. Keep that format.
        DexBuilder dex = new DexBuilder(new Opcodes(24));
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<Boolean>> results = new ArrayList<>();
            for (Path file : files) {
                results.add(pool.submit(() -> new SmaliBuilder(24).buildFile(file.toFile(), dex)));
            }
            for (int i = 0; i < results.size(); i++) {
                if (!results.get(i).get()) throw new IllegalStateException("Assembly failed: " + files.get(i));
            }
        } finally {
            pool.shutdownNow();
        }
        Path output = Path.of(args[1]);
        Files.createDirectories(output.toAbsolutePath().getParent());
        FileDataStore store = new FileDataStore(output.toFile());
        try { dex.writeTo(store); } finally { store.raf.close(); }
        System.out.println(output.getFileName() + ": assembled " + files.size() + " classes");
    }
}
