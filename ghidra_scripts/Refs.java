// Lists every reference to the given addresses, with the containing function.
// Headless usage: -postScript Refs.java <hex address> [<hex address> ...]
//@category NanoCam

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class Refs extends GhidraScript {

	@Override
	protected void run() throws Exception {
		for (String arg : getScriptArgs()) {
			Address addr = toAddr(Long.parseLong(arg.replace("0x", ""), 16));
			println("refs to " + addr + ":");
			for (Reference ref : getReferencesTo(addr)) {
				Function fn = getFunctionContaining(ref.getFromAddress());
				println(String.format("  %s %s in %s", ref.getFromAddress(), ref.getReferenceType(),
					fn == null ? "(no function)" : fn.getName() + " @ " + fn.getEntryPoint()));
			}
		}
	}
}
