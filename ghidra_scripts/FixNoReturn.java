// Clears a wrong "does not return" flag on functions and restores the code after their calls.
// Ghidra sometimes decides a function never returns (e.g. an allocator that can panic),
// then stops disassembling after every call to it. That truncates the callers.
// Headless usage (not -readOnly, so the fix is saved): -postScript FixNoReturn.java <hex address> ...
//@category iPodCamera

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class FixNoReturn extends GhidraScript {

	@Override
	protected void run() throws Exception {
		for (String arg : getScriptArgs()) {
			Function fn = getFunctionAt(toAddr(Long.parseLong(arg.replace("0x", ""), 16)));
			if (fn == null) {
				println(arg + ": no function here");
				continue;
			}
			fn.setNoReturn(false);

			int fixed = 0;
			for (Reference ref : getReferencesTo(fn.getEntryPoint())) {
				Instruction call = getInstructionAt(ref.getFromAddress());
				if (call == null || !ref.getReferenceType().isCall()) {
					continue;
				}
				call.clearFallThroughOverride();
				Address next = call.getDefaultFallThrough();
				if (next != null && getInstructionAt(next) == null) {
					// Keep the same ARM/Thumb mode as the call itself.
					disassemble(next);
					fixed++;
				}
			}
			println(String.format("%s: cleared no-return, re-disassembled after %d calls", fn.getName(), fixed));
		}
	}
}
