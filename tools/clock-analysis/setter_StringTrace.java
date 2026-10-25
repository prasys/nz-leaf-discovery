// setter-StringTrace.java - find defined strings matching a regex, list
// references to them, and decompile the referencing functions. Read-only.
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Pattern;

public class setter_StringTrace extends GhidraScript {
    private String clean(String s) {
        return s.replace("\n", "\\n").replace("\r", "\\r");
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Expected one string regex");
        Pattern wanted = Pattern.compile(args[0]);
        Set<Function> selected = new LinkedHashSet<>();
        println("SETTER-STRING-TRACE START " + args[0]);
        DataIterator it = currentProgram.getListing().getDefinedData(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Data d = it.next();
            if (!d.hasStringValue()) continue;
            String v = StringDataInstance.getStringDataInstance(d).getStringValue();
            if (v == null || !wanted.matcher(v).find()) continue;
            println("STR " + d.getAddress() + " \"" + clean(v) + "\"");
            for (Reference ref : getReferencesTo(d.getAddress())) {
                Function caller = getFunctionContaining(ref.getFromAddress());
                println("  REF " + ref.getFromAddress() + " "
                        + (caller == null ? "data" : caller.getName() + " @"
                                + caller.getEntryPoint()));
                if (caller != null && !caller.isThunk()) selected.add(caller);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        try {
            decompiler.openProgram(currentProgram);
            for (Function function : selected) {
                if (monitor.isCancelled()) break;
                println("FUNCTION " + function.getName() + " @ " + function.getEntryPoint());
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.getDecompiledFunction() == null) {
                    println("DECOMPILE FAILED " + result.getErrorMessage());
                } else {
                    println(result.getDecompiledFunction().getC());
                }
            }
        } finally {
            decompiler.dispose();
        }
        println("SETTER-STRING-TRACE COMPLETE: " + selected.size() + " functions");
    }
}
