// setter-RangeXref.java - scan all references and report those pointing into a
// given address range, decompiling referencing functions. Read-only.
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.util.LinkedHashSet;
import java.util.Set;

public class setter_RangeXref extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2)
            throw new IllegalArgumentException("Expected <loAddr> <hiAddr>");
        Address lo = currentProgram.getAddressFactory().getAddress(args[0]);
        Address hi = currentProgram.getAddressFactory().getAddress(args[1]);
        Set<Function> selected = new LinkedHashSet<>();
        println("SETTER-RANGEXREF START " + args[0] + ".." + args[1]);
        Address cur = lo;
        while (cur.compareTo(hi) <= 0 && !monitor.isCancelled()) {
            for (Reference r : currentProgram.getReferenceManager().getReferencesTo(cur)) {
                Function caller = getFunctionContaining(r.getFromAddress());
                println("REF from " + r.getFromAddress() + " -> " + cur + " "
                        + (caller == null ? "data" : caller.getName() + " @"
                                + caller.getEntryPoint()));
                if (caller != null && !caller.isThunk()) selected.add(caller);
            }
            cur = cur.next();
        }
        DecompInterface decompiler = new DecompInterface();
        try {
            decompiler.openProgram(currentProgram);
            for (Function function : selected) {
                if (monitor.isCancelled()) break;
                println("FUNCTION " + function.getName() + " @ " + function.getEntryPoint());
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.getDecompiledFunction() == null) {
                    println("DECOMPILE FAILED " + result.getErrorMessage());
                } else {
                    println(result.getDecompiledFunction().getC());
                }
            }
        } finally {
            decompiler.dispose();
        }
        println("SETTER-RANGEXREF COMPLETE: " + selected.size() + " functions");
    }
}
