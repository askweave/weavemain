from genesis.core.diagnostics import errors_only, failure_summary, parse_diagnostics

OUTPUT = """> Task :app:compileDebugKotlin FAILED
e: file:///Users/me/AI%20for%20us/data/builds/abc/workspace/app/src/main/java/com/genesis/app/ui/LogScreen.kt:149:33 Unresolved reference 'Vid'.
e: file:///Users/me/AI%20for%20us/data/builds/abc/workspace/app/src/main/java/com/genesis/app/ui/LogScreen.kt:149:33 Unresolved reference 'Vid'.
e: file:///Users/me/x/workspace/app/src/main/java/com/genesis/app/data/Store.kt:5:9 None of the following candidates is applicable:
    fun foo(a: Int): Unit
    fun foo(a: String): Unit
w: file:///Users/me/x/workspace/app/src/main/java/com/genesis/app/GenesisApp.kt:10:5 'Divider' is deprecated.
e: file:///Users/me/x/workspace/app/build.gradle.kts:3:1 Something in build script

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':app:compileDebugKotlin'.
> A failure occurred while executing org.jetbrains.kotlin.compilerRunner.GradleCompilerRunnerWithWorkers$GradleKotlinCompilerWorkAction
   > Compilation error. See log for more details

* Try:
> Run with --stacktrace option to get the stack trace.
"""


def test_parse_kotlin_diagnostics():
    diags = parse_diagnostics(OUTPUT)
    errs = errors_only(diags)
    assert len(errs) == 3  # duplicate collapsed
    multi = [d for d in errs if d.rel_path == "data/Store.kt"][0]
    assert multi.message.endswith("applicable: fun foo(a: Int): Unit | fun foo(a: String): Unit")
    assert errs[0].rel_path == "ui/LogScreen.kt"
    assert (errs[0].line, errs[0].column) == (149, 33)
    assert errs[0].render() == "error: ui/LogScreen.kt:149:33 Unresolved reference 'Vid'."
    assert errs[2].rel_path is None  # outside generated sources -> never sent for repair
    warns = [d for d in diags if d.severity == "warning"]
    assert warns[0].rel_path == "GenesisApp.kt"


def test_failure_summary():
    s = failure_summary(OUTPUT)
    assert s.startswith("Execution failed for task ':app:compileDebugKotlin'.")
    assert "Try" not in s
