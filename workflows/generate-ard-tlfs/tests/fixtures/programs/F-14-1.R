# @tlf F-14-1 analysis=AN.F-14-1 uses=ADSL.TRT01P,ADSL.SAFFL,ADAE.AEDECOD,ADAE.TRTEMFL
source("setup.R")
adsl <- read_adam("adsl")
adae <- merge(read_adam("adae"), adsl[, c("USUBJID", "TRT01P", "SAFFL")], by = "USUBJID")
adae <- adae[adae$TRTEMFL == "Y" & adae$SAFFL == "Y", ]
counts <- sapply(arms, function(arm) length(unique(adae$USUBJID[adae$TRT01P == arm])))
ard <- data.frame(group1 = "TRT01P", group1_level = arms, variable = "AEDECOD", context = "incidence", stat_name = "n", stat = as.numeric(counts))
ard <- rbind(ard, big_n(adsl[adsl$SAFFL == "Y", ]))
write_ard(ard, "F-14-1")
plot <- ggplot2::ggplot(ard[ard$variable == "AEDECOD", ], ggplot2::aes(x = factor(group1_level, levels = arms), y = stat)) + ggplot2::geom_col() +
  ggplot2::labs(x = NULL, y = "Subjects with a TEAE")
ggplot2::ggsave(file.path(Sys.getenv("TFL_DIR"), "F-14-1.png"), plot, width = 5, height = 3, dpi = 100)
