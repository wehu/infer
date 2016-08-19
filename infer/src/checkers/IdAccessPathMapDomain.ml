(*
 * Copyright (c) 2016 - present Facebook, Inc.
 * All rights reserved.
 *
 * This source code is licensed under the BSD style license found in the
 * LICENSE file in the root directory of this source tree. An additional grant
 * of patent rights can be found in the PATENTS file in the same directory.
 *)

open! Utils

(** mapping of ids to raw access paths. useful for id-normalizing access paths *)
module IdMap = PrettyPrintable.MakePPMap(struct
    type t = Ident.t
    let compare = Ident.compare
    let pp_key = (Ident.pp pe_text)
  end)

type astate = AccessPath.raw IdMap.t

include IdMap

let pp fmt astate =
  IdMap.pp ~pp_value:AccessPath.pp_raw fmt astate

let initial = IdMap.empty

let (<=) ~lhs ~rhs =
  if lhs == rhs
  then true
  else
    try
      IdMap.for_all
        (fun id lhs_ap ->
           let rhs_ap = IdMap.find id rhs in
           let eq = AccessPath.raw_equal lhs_ap rhs_ap in
           assert eq;
           eq)
        lhs
    with Not_found -> false

let join astate1 astate2 =
  if astate1 == astate2
  then astate1
  else
    IdMap.merge
      (fun _ ap1_opt ap2_opt -> match ap1_opt, ap2_opt with
         | Some ap1, Some ap2 ->
             (* in principle, could do a join here if the access paths have the same root. but
                they should always be equal if we are using the map correctly *)
             assert (AccessPath.raw_equal ap1 ap2);
             ap1_opt
         | Some _, None -> ap1_opt
         | None, Some _ -> ap2_opt
         | None, None -> None)
      astate1
      astate2

let widen ~prev ~next ~num_iters:_ =
  join prev next
