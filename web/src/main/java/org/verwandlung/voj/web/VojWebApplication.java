/* Verwandlung Online Judge - A cross-platform judge online system
 * Copyright (C) 2014-2026 Haozhe Xie <root@haozhexie.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
package org.verwandlung.voj.web;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.PropertySource;

import org.verwandlung.voj.web.model.ProblemImportReport;
import org.verwandlung.voj.web.service.ProblemImportCommand;

/**
 * The entry point of the web application of Verwandlung Online Judge.
 *
 * <p>The application is packaged as a self-contained executable JAR and runs standalone via {@code
 * java -jar voj.web.jar} with embedded Tomcat.
 *
 * @author Haozhe Xie
 */
@SpringBootApplication
@MapperScan("org.verwandlung.voj.web.mapper")
@PropertySource("classpath:voj.properties")
public class VojWebApplication extends SpringBootServletInitializer {
  /** The entry point of the application. */
  public static void main(String[] args) throws Exception {
    if (!ProblemImportMode.requested(args)) {
      SpringApplication.run(VojWebApplication.class, args);
      return;
    }
    SpringApplication application = new SpringApplication(VojWebApplication.class);
    application.setWebApplicationType(org.springframework.boot.WebApplicationType.NONE);
    try (ConfigurableApplicationContext context = application.run(args)) {
      ProblemImportCommand command = context.getBean(ProblemImportCommand.class);
      ProblemImportReport report =
          command.importPlan(
              ProblemImportMode.planPath(args), ProblemImportMode.mappingPath(args));
      System.out.println(command.toJson(report));
    }
    System.exit(ProblemImportMode.successExitCode());
  }

  /* (non-Javadoc)
   * When deployed to an external Servlet container, this method is invoked by the container to
   * assemble the application.
   */
  @Override
  protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
    return builder.sources(VojWebApplication.class);
  }
}
