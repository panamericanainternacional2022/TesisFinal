CREATE TABLE `Usuario` (
  `id_usuario` int AUTO_INCREMENT PRIMARY KEY,
  `username` text,
  `password` text,
  `id_persona` int
);

CREATE TABLE `persona` (
  `id_persona` int AUTO_INCREMENT PRIMARY KEY,
  `ci` int,
  `name` text,
  `apellido` text,
  `email` text,
  `telefono` text
);

CREATE TABLE `edificio` (
  `id_edificio` int AUTO_INCREMENT PRIMARY KEY,
  `nb_edificio` text,
  `rif` int,
  `direccion` text
);

CREATE TABLE `equipo_monitoreo` (
  `id_equipo_monitoreo` int AUTO_INCREMENT PRIMARY KEY,
  `nb_equipo` text,
  `id_edificio` int
);

CREATE TABLE `usuario_edificio` (
  `id_usuario_beneficiario` int AUTO_INCREMENT PRIMARY KEY,
  `id_usuario` int,
  `id_edificio` int
);

CREATE TABLE `dispos_sensor` (
  `id_dispos_sensor` int AUTO_INCREMENT PRIMARY KEY,
  `nb_sensor` text,
  `modelo_iot` text
);

CREATE TABLE `equipo_sensor` (
  `id_equipo_sensor` int AUTO_INCREMENT PRIMARY KEY,
  `id_equipo_monitoreo` int,
  `id_dispos_sensor` int,
  `tipo_valor_capt` float,
  `fecha_hora_lect` datetime,
  `descripcion_falla` text
);

CREATE TABLE `status` (
  `id_status` int AUTO_INCREMENT PRIMARY KEY,
  `nb_status` text
);

CREATE TABLE `status_equipo_monitoreo` (
  `id_status_equipo_monitoreo` int AUTO_INCREMENT PRIMARY KEY,
  `id_status` int,
  `id_equipo_monitoreo` int
);

CREATE TABLE `accion_prev` (
  `id_accion_prev` int AUTO_INCREMENT PRIMARY KEY,
  `id_equipo_monitoreo` int,
  `id_dispos_sensor` int,
  `parametro` text,
  `valor_min` float,
  `valor_max` float,
  `accion_preventiva` text,
  `id_status` int
);

CREATE TABLE `notificacion` (
  `id_notificacion` int AUTO_INCREMENT PRIMARY KEY,
  `id_usuario` int,
  `id_equipo_monitoreo` int,
  `fecha` datetime,
  `mensaje` text
);

CREATE TABLE `historico_falla` (
  `id_historico_falla` int AUTO_INCREMENT PRIMARY KEY,
  `id_equipo_sensor` int,
  `fecha` datetime,
  `id_status_equipo_monitoreo` int
);

ALTER TABLE `Usuario` ADD FOREIGN KEY (`id_persona`) REFERENCES `persona` (`id_persona`);

ALTER TABLE `usuario_edificio` ADD FOREIGN KEY (`id_usuario`) REFERENCES `Usuario` (`id_usuario`);

ALTER TABLE `usuario_edificio` ADD FOREIGN KEY (`id_edificio`) REFERENCES `edificio` (`id_edificio`);

ALTER TABLE `equipo_monitoreo` ADD FOREIGN KEY (`id_edificio`) REFERENCES `edificio` (`id_edificio`);

ALTER TABLE `status_equipo_monitoreo` ADD FOREIGN KEY (`id_status`) REFERENCES `status` (`id_status`);

ALTER TABLE `status_equipo_monitoreo` ADD FOREIGN KEY (`id_equipo_monitoreo`) REFERENCES `equipo_monitoreo` (`id_equipo_monitoreo`);

ALTER TABLE `historico_falla` ADD FOREIGN KEY (`id_status_equipo_monitoreo`) REFERENCES `status_equipo_monitoreo` (`id_status_equipo_monitoreo`);

ALTER TABLE `equipo_sensor` ADD FOREIGN KEY (`id_equipo_monitoreo`) REFERENCES `equipo_monitoreo` (`id_equipo_monitoreo`);

ALTER TABLE `equipo_sensor` ADD FOREIGN KEY (`id_dispos_sensor`) REFERENCES `dispos_sensor` (`id_dispos_sensor`);

ALTER TABLE `historico_falla` ADD FOREIGN KEY (`id_equipo_sensor`) REFERENCES `equipo_sensor` (`id_equipo_sensor`);

ALTER TABLE `accion_prev` ADD FOREIGN KEY (`id_equipo_monitoreo`) REFERENCES `equipo_monitoreo` (`id_equipo_monitoreo`);

ALTER TABLE `accion_prev` ADD FOREIGN KEY (`id_dispos_sensor`) REFERENCES `dispos_sensor` (`id_dispos_sensor`);

ALTER TABLE `accion_prev` ADD FOREIGN KEY (`id_status`) REFERENCES `status` (`id_status`);

ALTER TABLE `notificacion` ADD FOREIGN KEY (`id_usuario`) REFERENCES `Usuario` (`id_usuario`);

ALTER TABLE `notificacion` ADD FOREIGN KEY (`id_equipo_monitoreo`) REFERENCES `equipo_monitoreo` (`id_equipo_monitoreo`);
