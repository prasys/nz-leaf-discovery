// Export matching functions and direct callers without modifying the program.
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Pattern;

public class ClockTrace extends GhidraScript {
    private void collect(Symbol symbol, Pattern wanted, Set<Function> selected) {
        if (!wanted.matcher(symbol.getName(true)).find()) return;
        println("MATCH " + symbol.getName(true) + " @ " + symbol.getAddress());
        Function own = getFunctionAt(symbol.getAddress());
        if (own != null && !own.isExternal() && !own.isThunk()) selected.add(own);
        for (Reference ref : getReferencesTo(symbol.getAddress())) {
            Function caller = getFunctionContaining(ref.getFromAddress());
            println("REF " + ref.getFromAddress() + " " + (caller == null ? "data" : caller.getName()));
            if (caller != null && !caller.isExternal() && !caller.isThunk()) selected.add(caller);
            if (caller != null && caller.isThunk()) {
                for (Reference indirect : getReferencesTo(caller.getEntryPoint())) {
                    Function parent = getFunctionContaining(indirect.getFromAddress());
                    if (parent != null && !parent.isExternal() && !parent.isThunk()) selected.add(parent);
                }
            }
        }
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Expected one name regex");
        Pattern wanted = Pattern.compile(args[0]);
        Set<Function> selected = new LinkedHashSet<>();
        SymbolIterator symbols = currentProgram.getSymbolTable().getAllSymbols(true);
        while (symbols.hasNext() && !monitor.isCancelled()) {
            collect(symbols.next(), wanted, selected);
        }
        symbols = currentProgram.getSymbolTable().getExternalSymbols();
        while (symbols.hasNext() && !monitor.isCancelled()) collect(symbols.next(), wanted, selected);
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
        println("CLOCK TRACE COMPLETE: " + selected.size() + " functions");
    }
}
