// execution-: decompile the functions containing the given addresses (read-only).
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.util.LinkedHashSet;
import java.util.Set;

public class execution_DecompAt extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) throw new IllegalArgumentException("Expected address list");
        java.util.List<String> addrs = new java.util.ArrayList<>();
        for (String arg : args) {
            for (String part : arg.split(",")) {
                if (!part.isBlank()) addrs.add(part.trim());
            }
        }
        Set<Function> selected = new LinkedHashSet<>();
        for (String arg : addrs) {
            Address addr = currentProgram.getAddressFactory().getAddress(arg.replaceFirst("^0x", ""));
            Function f = getFunctionContaining(addr);
            if (f == null) f = getFunctionAt(addr);
            if (f == null) {
                println("NO FUNCTION AT " + arg);
            } else {
                println("SEL " + f.getName() + " @ " + f.getEntryPoint());
                selected.add(f);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        try {
            decompiler.openProgram(currentProgram);
            for (Function function : selected) {
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                println("FUNCTION " + function.getName() + " @ " + function.getEntryPoint());
                if (result.getDecompiledFunction() == null) {
                    println("DECOMPILE FAILED " + result.getErrorMessage());
                } else {
                    println(result.getDecompiledFunction().getC());
                }
            }
        } finally {
            decompiler.dispose();
        }
        println("DECOMPAT COMPLETE: " + selected.size());
    }
}
