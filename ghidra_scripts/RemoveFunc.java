// Removes wrongly-created function definitions (e.g. a mid-function block Ghidra
// split off), so the real enclosing function decompiles as one piece.
// Headless usage (not -readOnly, so the change is saved): -postScript RemoveFunc.java <hex address> ...
//@category iPodCamera

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class RemoveFunc extends GhidraScript {

	@Override
	protected void run() throws Exception {
		for (String arg : getScriptArgs()) {
			Function f = getFunctionAt(toAddr(Long.parseLong(arg.replace("0x", ""), 16)));
			if (f == null) {
				println("no function at " + arg);
				continue;
			}
			String name = f.getName();
			removeFunction(f);
			println("removed " + name);
		}
	}
}
