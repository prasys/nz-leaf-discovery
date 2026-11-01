// Decompile callers of specified string/data addresses. Static inspection only.
// @category Nissan.Speech
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;

public class SpeechRefs extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Set<Function> selected = new LinkedHashSet<>();
        DecompInterface dc = new DecompInterface();
        try (PrintWriter out = new PrintWriter(args[0], StandardCharsets.UTF_8)) {
            dc.openProgram(currentProgram);
            for (int i = 1; i < args.length; i++) {
                for (Reference r : getReferencesTo(toAddr(args[i]))) {
                    out.println("REF " + args[i] + " FROM " + r.getFromAddress());
                    Function f = getFunctionContaining(r.getFromAddress());
                    if (f != null) selected.add(f);
                }
            }
            for (Function f : selected) {
                out.println("FUNCTION " + f.getName() + " @ " + f.getEntryPoint());
                var result = dc.decompileFunction(f, 60, monitor);
                if (result.getDecompiledFunction() != null)
                    out.println(result.getDecompiledFunction().getC());
                else out.println("FAILED " + result.getErrorMessage());
            }
            out.println("SPEECH REFS COMPLETE " + selected.size());
        } finally { dc.dispose(); }
    }
}
