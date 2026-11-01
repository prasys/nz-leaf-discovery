// Export selected functions, their callers, and callees for static speech analysis.
// @category Nissan.Speech
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;

public class SpeechTrace extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 3) throw new IllegalArgumentException("output depth hex-address ...");
        Set<Function> selected = new LinkedHashSet<>();
        for (int i = 2; i < args.length; i++) {
            Function f = getFunctionContaining(toAddr(args[i]));
            if (f == null) f = createFunction(toAddr(args[i]), null);
            if (f == null) throw new IllegalArgumentException("No function at " + args[i]);
            selected.add(f);
        }
        int depth = Integer.parseInt(args[1]);
        for (int i = 0; i < depth; i++) {
            Set<Function> more = new LinkedHashSet<>();
            for (Function f : selected) more.addAll(f.getCalledFunctions(monitor));
            selected.addAll(more);
        }
        DecompInterface dc = new DecompInterface();
        try (PrintWriter out = new PrintWriter(args[0], StandardCharsets.UTF_8)) {
            dc.openProgram(currentProgram);
            out.println("PROGRAM " + currentProgram.getName() + " " + currentProgram.getLanguageID());
            int count = 0;
            for (Function f : selected) {
                if (f.isExternal() || f.isThunk()) continue;
                out.println("FUNCTION " + f.getName() + " @ " + f.getEntryPoint());
                for (Function caller : f.getCallingFunctions(monitor))
                    out.println("CALLER " + caller.getName() + " @ " + caller.getEntryPoint());
                DecompileResults result = dc.decompileFunction(f, 60, monitor);
                if (result.getDecompiledFunction() == null)
                    out.println("FAILED " + result.getErrorMessage());
                else out.println(result.getDecompiledFunction().getC());
                InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    out.println(ins.getAddress() + " " + ins);
                }
                count++;
            }
            out.println("SPEECH TRACE COMPLETE " + count);
        } finally { dc.dispose(); }
    }
}
