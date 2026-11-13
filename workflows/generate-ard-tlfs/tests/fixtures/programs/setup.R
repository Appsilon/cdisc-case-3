read_adam <- function(name) haven::read_xpt(file.path(Sys.getenv("ADAM_DIR"), paste0(name, ".xpt")))
sas_round <- function(x, digits = 0) sign(x) * floor(abs(x) * 10^digits + 0.5) / 10^digits
fmt <- function(x, digits) formatC(sas_round(x, digits), format = "f", digits = digits)
write_ard <- function(ard, id) jsonlite::write_json(ard, file.path(Sys.getenv("ARD_DIR"), paste0(id, ".json")), auto_unbox = TRUE, digits = NA)
arms <- unique(read_adam("adsl")$TRT01P)
big_n <- function(adsl) data.frame(group1 = "TRT01P", group1_level = arms, variable = "BIGN", context = "SAFFL = Y", stat_name = "N",
                                   stat = as.numeric(sapply(arms, function(arm) sum(adsl$TRT01P == arm))))
ard_row <- function(ard, ...) {
  wanted <- list(...)
  index <- which(Reduce(`&`, Map(function(column, value) ard[[column]] == value, names(wanted), wanted)))
  stopifnot(length(index) == 1)
  index - 1
}
td <- function(text, rows) paste0("<td data-ard='", paste(rows, collapse = ","), "'>", text, "</td>")
