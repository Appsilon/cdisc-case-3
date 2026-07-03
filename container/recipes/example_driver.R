# Reference driver for the generate-tfl AGENT: binds the 7 CDISCPILOT01 ARS
# outputs to ADaM, runs recipes for the 5 standard safety outputs and drafts
# programs for the 2 custom efficacy outputs, all emitting the long-skinny ARD
# contract + a rendered display, plus coverage.json. This is a WORKING template
# (it integration-tests package.R and is the SKILL.md worked example). The agent
# adapts it to the ARS + ADaM it is actually given.
#
# Paths: in the container, recipes live at /app/container/recipes and the staged
# ADaM at /workspace/adam; RECIPES/ADAM/WORK env vars override for local runs.
if (nzchar(Sys.getenv("RLIB"))) .libPaths(c(Sys.getenv("RLIB"), .libPaths()))
suppressMessages({library(dplyr); library(jsonlite); library(cards); library(gt); library(gtsummary)})
RECIPES <- Sys.getenv("RECIPES", "/app/container/recipes")
source(file.path(RECIPES, "recipes.R"))
adam <- Sys.getenv("ADAM", "/workspace/adam")
work <- Sys.getenv("WORK", "/workspace"); dir.create(file.path(work,"ard"), recursive=TRUE, showWarnings=FALSE)
dir.create(file.path(work,"tfl"), recursive=TRUE, showWarnings=FALSE)
rd <- function(f) read.csv(file.path(adam,f), stringsAsFactors=FALSE)
adsl <- rd("adsl.csv"); adae <- rd("adae.csv"); advs <- rd("advs.csv")
adqs <- rd("adqsadas.csv"); adtte <- rd("adtte.csv")
adsl_saf <- filter(adsl, SAFFL=="Y"); adsl_itt <- filter(adsl, ITTFL=="Y")
OPMAP_CONT <- c(N="Mth02_ContVar_Summ_ByGrp_1_n", mean="Mth02_ContVar_Summ_ByGrp_2_Mean",
  sd="Mth02_ContVar_Summ_ByGrp_3_SD", median="Mth02_ContVar_Summ_ByGrp_4_Median",
  p25="Mth02_ContVar_Summ_ByGrp_5_Q1", p75="Mth02_ContVar_Summ_ByGrp_6_Q3",
  min="Mth02_ContVar_Summ_ByGrp_7_Min", max="Mth02_ContVar_Summ_ByGrp_8_Max")
OPMAP_CAT <- c(n="Mth01_CatVar_Summ_ByGrp_1_n", p="Mth01_CatVar_Summ_ByGrp_2_pct", N="Mth01_CatVar_Summ_ByGrp_1_n")

# 1. Demographics (standard)
r <- recipe_demographics(adsl_saf, "Out14-1-1", "An01_05_SAF_Summ_ByTrt",
  group_var="TRT01P", cont_vars="AGE", cat_vars=c("SEX","RACE"),
  operation_map=c(OPMAP_CONT, OPMAP_CAT)); write_output(r$long, r$gt, "Out14-1-1", work)

# 2. Overall TEAE summary (standard) — subjects with >=1 TEAE by arm
teae <- adae %>% filter(TRTEMFL=="Y") %>% distinct(USUBJID, TRT01A) %>% mutate(ANYAE="Y")
ov <- ard_categorical(data=teae, variables=ANYAE, by=TRT01A, statistic=~c("n","N","p"))
write_output(ard_to_long(ov, "Out14-3-1-1", "An_ov_teae", OPMAP_CAT), as_gt(tbl_ard_summary(cards=ov, by=TRT01A, include=ANYAE)), "Out14-3-1-1", work)

# 3. AE by SOC/PT (standard)
r <- recipe_ae_soc_pt(adae, adsl_saf, "Out14-3-2-1", "An_ae_socpt", operation_map=OPMAP_CAT)
write_output(r$long, r$gt, "Out14-3-2-1", work)

# 4a/4b. Vital signs observed + change (standard) — summarize AVAL & CHG by arm
vs <- advs %>% filter(PARAMCD=="SYSBP_SUPINE", ABLFL!="Y", !is.na(CHG))
for (oid in c("Out14-3-3-1a","Out14-3-3-1b")) {
  r <- recipe_summary_by_group(vs, oid, "An_vs", group_var="TRT01A",
    cont_vars=c("AVAL","CHG"), operation_map=OPMAP_CONT); write_output(r$long, r$gt, oid, work)
}

# 5. CUSTOM: ADAS-Cog Week 24 ANCOVA (agent-drafted program) -> long-skinny ARD
suppressMessages({library(emmeans)})
ad <- adqs %>% filter(PARAMCD=="ACTOT", AVISITN==24, ANL01FL=="Y", ITTFL=="Y", !is.na(CHG))
fit <- lm(CHG ~ TRT01P + BASE, data=ad)
emm <- as.data.frame(emmeans(fit, "TRT01P"))
pbo <- "Placebo"
ct <- as.data.frame(pairs(emmeans(fit,"TRT01P"), reverse=TRUE))
mklong <- function(op, level, name, label, raw, fmt) data.frame(output_id="Out14-3-01",
  analysis_id="AnEff01_ADAS_Wk24_ANCOVA", operation_id=op, group_var="TRT01P", group_level=level,
  variable="CHG", variable_level=NA_character_, stat_name=name, stat_label=label,
  stat_raw=as.character(raw), stat_fmt=fmt, stringsAsFactors=FALSE)
rows <- do.call(rbind, lapply(seq_len(nrow(emm)), function(i) rbind(
  mklong("MthEff01_ANCOVA_ChgBl_2_LSMean", emm$TRT01P[i], "lsmean","LS Mean", emm$emmean[i], sprintf("%.1f",emm$emmean[i])),
  mklong("MthEff01_ANCOVA_ChgBl_3_LSMeanSE", emm$TRT01P[i], "se","SE", emm$SE[i], sprintf("(%.2f)",emm$SE[i])))))
# differences vs placebo
diffrows <- do.call(rbind, lapply(seq_len(nrow(ct)), function(i) {
  lv <- ct$contrast[i]
  rbind(mklong("MthEff01_ANCOVA_ChgBl_4_Diff", lv, "diff","Diff vs PBO", ct$estimate[i], sprintf("%.1f",ct$estimate[i])),
        mklong("MthEff01_ANCOVA_ChgBl_7_pval", lv, "pval","p-value", ct$p.value[i], sprintf("%.3f",ct$p.value[i])))}))
adas_long <- rbind(rows, diffrows)
write.csv(adas_long, file.path(work,"ard","Out14-3-01.csv"), row.names=FALSE, na="")
gt::gtsave(gt::gt(emm), file.path(work,"tfl","Out14-3-01.html"))
cat("wrote custom code file\n")
writeLines(c("# Agent-drafted ANCOVA program (custom output Out14-3-01)","# lm(CHG ~ TRT01P + BASE); emmeans LS means + pairwise vs placebo"),
           file.path(work,"code_Out14-3-01.R"))

# 6. CUSTOM: Time-to-event Kaplan-Meier (agent-drafted) -> long-skinny ARD
suppressMessages({library(survival)})
tte <- adtte %>% filter(PARAMCD=="TTDE" | is.na(PARAMCD)) ; if(nrow(tte)==0) tte <- adtte
tte <- tte %>% mutate(event=1-CNSR)
sf <- survfit(Surv(AVAL, event) ~ TRT01P, data=tte)
med <- summary(sf)$table
cox <- tryCatch(coxph(Surv(AVAL,event) ~ relevel(factor(TRT01P), ref="Placebo"), data=tte), error=function(e) NULL)
kmlong <- do.call(rbind, lapply(rownames(med), function(rn){
  lvl <- sub("TRT01P=","",rn)
  data.frame(output_id="Out14-KM-01", analysis_id="AnEff02_TTE_KM",
    operation_id="MthEff02_KM_TTE_2_Median", group_var="TRT01P", group_level=lvl, variable="AVAL",
    variable_level=NA_character_, stat_name="median", stat_label="Median (days)",
    stat_raw=as.character(med[rn,"median"]), stat_fmt=sprintf("%.1f", as.numeric(med[rn,"median"])), stringsAsFactors=FALSE)}))
write.csv(kmlong, file.path(work,"ard","Out14-KM-01.csv"), row.names=FALSE, na="")
png(file.path(work,"tfl","Out14-KM-01.png"), width=900, height=600); plot(sf, col=1:3, xlab="Days", ylab="Survival"); dev.off()
writeLines(c("# Agent-drafted Kaplan-Meier program (custom output Out14-KM-01)","# survfit(Surv(AVAL,1-CNSR) ~ TRT01P); coxph HR vs placebo"),
           file.path(work,"code_Out14-KM-01.R"))

# coverage.json — the classification the reviewer + demo see
coverage <- list(outputs=list(
  list(outputId="Out14-1-1", mode="standard", recipe="recipe_demographics", analysisIds=list("An01_05_SAF_Summ_ByTrt"), status="rendered", repairs=list()),
  list(outputId="Out14-3-1-1", mode="standard", recipe="ard_categorical", analysisIds=list("An_ov_teae"), status="rendered", repairs=list()),
  list(outputId="Out14-3-2-1", mode="standard", recipe="recipe_ae_soc_pt", analysisIds=list("An_ae_socpt"), status="rendered", repairs=list()),
  list(outputId="Out14-3-3-1a", mode="standard", recipe="recipe_summary_by_group", analysisIds=list("An_vs"), status="rendered", repairs=list()),
  list(outputId="Out14-3-3-1b", mode="standard", recipe="recipe_summary_by_group", analysisIds=list("An_vs"), status="rendered", repairs=list()),
  list(outputId="Out14-3-01", mode="custom", program="code_Out14-3-01.R", analysisIds=list("AnEff01_ADAS_Wk24_ANCOVA"), status="rendered",
       repairs=list("bound ANCOVA to ADQSADAS.CHG at AVISITN=24, ANL01FL=Y; baseline covariate = BASE")),
  list(outputId="Out14-KM-01", mode="custom", program="code_Out14-KM-01.R", analysisIds=list("AnEff02_TTE_KM"), status="rendered",
       repairs=list("bound KM to ADTTE Surv(AVAL, 1-CNSR); Cox HR vs Placebo reference"))
))
write_json(coverage, file.path(work,"coverage.json"), auto_unbox=TRUE, pretty=TRUE)
cat("Emulated 7 outputs. ard files:", length(list.files(file.path(work,"ard"))), "| tfl files:", length(list.files(file.path(work,"tfl"))), "\n")
