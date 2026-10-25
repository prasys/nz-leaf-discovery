// setter-Xref.java - list references to given addresses and decompile the
// referencing functions. Read-only; useful for dispatch tables and data refs.
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.util.LinkedHashSet;
import java.util.Set;

public class setter_Xref extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) throw new IllegalArgumentException("Expected address(es)");
        Set<Function> selected = new LinkedHashSet<>();
        println("SETTER-XREF START");
        for (String a : args) {
            Address addr = currentProgram.getAddressFactory().getAddress(a);
            if (addr == null) {
                println("BAD ADDR " + a);
                continue;
            }
            println("TARGET " + addr);
            for (Reference ref : getReferencesTo(addr)) {
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
        println("SETTER-XREF COMPLETE: " + selected.size() + " functions");
    }
}
