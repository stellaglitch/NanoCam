// Decompiles functions to C and lists who calls them.
// Headless usage: -postScript Decompile.java <hex address> [<hex address> ...]
// An address inside a function decompiles the whole function. If no function exists
// there yet, one is created. Add a "t" suffix (e.g. 0809c478t) to disassemble it as Thumb.
//@category iPodCamera

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class Decompile extends GhidraScript {

	@Override
	protected void run() throws Exception {
		DecompInterface decomp = new DecompInterface();
		decomp.openProgram(currentProgram);

		for (String arg : getScriptArgs()) {
			boolean thumb = arg.endsWith("t");
			Address addr = toAddr(Long.parseLong(arg.replace("0x", "").replace("t", ""), 16));
			Function fn = getFunctionContaining(addr);
			if (fn == null) {
				if (thumb) {
					// Code here may already be wrongly decoded as ARM. Clear it so it can be
					// redone as Thumb. Run with -readOnly when unsure, so nothing is saved.
					Instruction old = getInstructionContaining(addr);
					clearListing(old != null ? old.getMinAddress() : addr, addr.add(0x3ff));
					// TMode is Ghidra's ARM context flag: 1 = decode as Thumb.
					currentProgram.getProgramContext().setValue(
						currentProgram.getProgramContext().getRegister("TMode"), addr, addr,
						java.math.BigInteger.ONE);
				}
				disassemble(addr);
				fn = createFunction(addr, null);
			}
			if (fn == null) {
				println("==== " + addr + ": could not create a function here");
				continue;
			}

			// Disassemble code that was skipped after calls wrongly thought not to return,
			// then let Ghidra recompute the function's extent.
			for (int pass = 0; pass < 8; pass++) {
				boolean grew = false;
				for (Instruction insn : currentProgram.getListing().getInstructions(fn.getBody(), true)) {
					Address next = insn.getFlowType().isCall() ? insn.getDefaultFallThrough() : null;
					if (next != null) {
						insn.clearFallThroughOverride();
						if (getInstructionAt(next) == null) {
							// Bytes after the call may have been marked as data; clear them first.
							if (getDataAt(next) != null) {
								clearListing(next);
							}
							if (disassemble(next)) {
								grew = true;
								println("  restored code after call at " + insn.getAddress());
							}
						}
					}
				}
				ghidra.app.cmd.function.CreateFunctionCmd.fixupFunctionBody(currentProgram, fn, monitor);
				if (!grew) {
					break;
				}
			}

			println("==== " + fn.getName() + " @ " + fn.getEntryPoint());
			StringBuilder callers = new StringBuilder();
			for (Reference ref : getReferencesTo(fn.getEntryPoint())) {
				Function caller = getFunctionContaining(ref.getFromAddress());
				callers.append(String.format("  %s (%s)", ref.getFromAddress(),
					caller == null ? "?" : caller.getName()));
			}
			println("callers:" + (callers.length() == 0 ? " none found" : callers));

			DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
			println(res.decompileCompleted() ? res.getDecompiledFunction().getC()
					: "decompile failed: " + res.getErrorMessage());
		}
		decomp.dispose();
	}
}
