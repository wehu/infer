/*
 * Copyright (c) 2016 - present Facebook, Inc.
 * All rights reserved.
 *
 * This source code is licensed under the BSD style license found in the
 * LICENSE file in the root directory of this source tree. An additional grant
 * of patent rights can be found in the PATENTS file in the same directory.
 */

package endtoend.cpp.infer;

import static org.hamcrest.MatcherAssert.assertThat;
import static utils.matchers.ResultContainsExactly.containsExactly;


import com.google.common.collect.ImmutableList;

import org.junit.BeforeClass;
import org.junit.ClassRule;
import org.junit.Test;

import java.io.IOException;

import utils.DebuggableTemporaryFolder;
import utils.InferException;
import utils.InferResults;
import utils.InferRunner;

public class SkipFunctionWithConstFormalsTest {

  public static final String FILE =
      "infer/tests/codetoanalyze/cpp/errors/npe/skip_function_with_const_formals.cpp";

  private static ImmutableList<String> inferCmd;

  public static final String NULL_DEREFERENCE = "NULL_DEREFERENCE";

  @ClassRule
  public static DebuggableTemporaryFolder folder =
      new DebuggableTemporaryFolder();

  @BeforeClass
  public static void runInfer() throws InterruptedException, IOException {
    inferCmd = InferRunner.createCPPInferCommand(folder, FILE);
  }

  @Test
  public void whenInferRunsNullDerefFunctionsErrorIsFound()
      throws InterruptedException, IOException, InferException {
    String[] procedures = {
      "skip_then_split_case",
      "typedef_skip_then_split_case", // Infer should not report there
                                      // but currently we don't look
                                      // at const qualifiers
                                      // underneath typedef's
    };
    InferResults inferResults = InferRunner.runInferCPP(inferCmd);
    assertThat(
        "Results should contain null dereference",
        inferResults,
        containsExactly(
            NULL_DEREFERENCE,
            FILE,
            procedures
        )
    );
  }
}
