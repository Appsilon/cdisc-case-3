read_adam <- function(name) haven::read_xpt(file.path(Sys.getenv("ADAM_DIR"), paste0(name, ".xpt")))
sas_round <- function(x, digits = 0) sign(x) * floor(abs(x) * 10^digits + 0.5) / 10^digits
fmt <- function(x, digits) formatC(sas_round(x, digits), format = "f", digits = digits)
write_ard <- function(ard, id) jsonlite::write_json(ard, file.path(Sys.getenv("ARD_DIR"), paste0(id, ".json")), auto_unbox = TRUE, digits = NA)
arms <- c("Placebo", "Drug Low", "Drug High")
