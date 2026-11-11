# @tlf T-14-2.01 analysis=AN.T-14-2.01 uses=ADSL.SAFFL,ADSL.TRT01P,ADSL.AGE
source("setup.R")
adsl <- read_adam("adsl")
adsl <- adsl[adsl$SAFFL == "Y", ]
ard <- do.call(rbind, lapply(arms, function(arm) {
  age <- adsl$AGE[adsl$TRT01P == arm]
  data.frame(group1 = "TRT01P", group1_level = arm, variable = "AGE", context = "continuous",
             stat_name = c("N", "mean", "sd"), stat = c(length(age), mean(age), sd(age)))
}))
write_ard(ard, "T-14-2.01")
cell <- function(arm, stat) ard$stat[ard$group1_level == arm & ard$stat_name == stat]
rows <- c(
  paste0("<tr><td>n</td>", paste0("<td>", sapply(arms, function(arm) fmt(cell(arm, "N"), 0)), "</td>", collapse = ""), "</tr>"),
  paste0("<tr><td>Mean (SD)</td>", paste0("<td>", sapply(arms, function(arm) paste0(fmt(cell(arm, "mean"), 1), " (", fmt(cell(arm, "sd"), 2), ")")), "</td>", collapse = ""), "</tr>")
)
writeLines(c("<table>", paste0("<tr><th>Age (years)</th>", paste0("<th>", arms, "</th>", collapse = ""), "</tr>"), rows, "</table>"),
           file.path(Sys.getenv("TFL_DIR"), "T-14-2.01.html"))
