// execution-: list matching symbol names only (no decompilation, read-only).
// @category Nissan.Clock
import ghidra.app.script.GhidraScript;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import java.util.regex.Pattern;

public class execution_SymList extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Expected one name regex");
        Pattern wanted = Pattern.compile(args[0]);
        SymbolIterator symbols = currentProgram.getSymbolTable().getAllSymbols(true);
        while (symbols.hasNext()) {
            Symbol symbol = symbols.next();
            String name = symbol.getName(true);
            if (wanted.matcher(name).find()) {
                println("SYM " + name + " @ " + symbol.getAddress());
            }
        }
        println("SYMLIST COMPLETE");
    }
}
