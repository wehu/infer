/*
 * Copyright (c) 2015 - present Facebook, Inc.
 * All rights reserved.
 *
 * This source code is licensed under the BSD style license found in the
 * LICENSE file in the root directory of this source tree. An additional grant
 * of patent rights can be found in the PATENTS file in the same directory.
 */

package endtoend.objc.linters;

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

public class RegisteredObserver2 {

  public static final String VCFile2 =
      "infer/tests/codetoanalyze/objc/linters/registered_observer/ViewController2.m";

  private static ImmutableList<String> inferCmd;

  public static final String REGISTERED_OBSERVER = "REGISTERED_OBSERVER_BEING_DEALLOCATED";

  @ClassRule
  public static DebuggableTemporaryFolder folder = new DebuggableTemporaryFolder();

  @BeforeClass
  public static void runInfer() throws InterruptedException, IOException {
    inferCmd = InferRunner.createObjCLintersCommandSimple(
        folder,
        VCFile2);
  }

  @Test
  public void RegisteredObserverShouldNotBeFound()
      throws InterruptedException, IOException, InferException {
    InferResults inferResults = InferRunner.runInferObjC(inferCmd);
    String[] methods = {};
    assertThat(
        "Results should contain " + REGISTERED_OBSERVER,
        inferResults,
        containsExactly(
            REGISTERED_OBSERVER,
            VCFile2,
            methods
        )
    );
  }

}
